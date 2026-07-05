from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"N8NB"
HEADER_LEN_BYTES = 4
FORMAT_SCHEMA = 1
MAX_HEADER_LEN = 64 * 1024

DEK_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
SALT_BYTES = 16
KEK_BYTES = 32

CIPHER = "aes-256-gcm"
KDF = "argon2id"
SlotType = Literal["passphrase", "recovery"]


@dataclass(frozen=True)
class KdfParams:
    time_cost: int = 3
    memory_cost: int = 65536
    parallelism: int = 4

    def as_header(self) -> dict[str, int]:
        return {"m": self.memory_cost, "p": self.parallelism, "t": self.time_cost}


DEFAULT_KDF_PARAMS = KdfParams()


class CryptoError(Exception):
    """Base class for local-n8n bundle crypto failures."""


class BundleFormatError(CryptoError):
    """Raised when a bundle frame/header is malformed or unsupported."""


class BundleAuthenticationError(CryptoError):
    """Raised when a bundle cannot be authenticated with the provided secret."""


@dataclass(frozen=True)
class BundlePlaintext:
    payload: bytes
    slot_type: SlotType
    header: Mapping[str, Any]


def seal_bundle(
    payload: bytes,
    *,
    passphrase: str | bytes,
    recovery_code: str | bytes,
    random_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> bytes:
    """Seal bytes into a local-n8n encrypted bundle.

    Phase 3a deliberately handles only bytes. Backup/restore code will assemble
    manifests and volume archives before calling this library.
    """
    if not payload:
        raise ValueError("payload must not be empty")

    dek = _random_exact(random_bytes, DEK_BYTES)
    payload_nonce = _random_exact(random_bytes, NONCE_BYTES)
    ciphertext_length = len(payload) + TAG_BYTES
    slots = [
        _wrap_slot("passphrase", passphrase, dek, random_bytes),
        _wrap_slot("recovery", recovery_code, dek, random_bytes),
    ]
    header = {
        "cipher": CIPHER,
        "format_schema": FORMAT_SCHEMA,
        "kdf": KDF,
        "kdf_params": DEFAULT_KDF_PARAMS.as_header(),
        "magic": MAGIC.decode("ascii"),
        "payload": {
            "ciphertext_length": ciphertext_length,
            "nonce": _b64encode(payload_nonce),
        },
        "slots": slots,
    }
    header_bytes = _canonical_json_bytes(header)
    if len(header_bytes) > MAX_HEADER_LEN:
        raise BundleFormatError("bundle header is too large")

    ciphertext = AESGCM(dek).encrypt(payload_nonce, payload, header_bytes)
    return MAGIC + len(header_bytes).to_bytes(HEADER_LEN_BYTES, "big") + header_bytes + ciphertext


def open_bundle(
    bundle: bytes,
    *,
    secret: str | bytes,
    slot_type: SlotType | None = None,
) -> BundlePlaintext:
    """Open an encrypted bundle with either the passphrase or recovery code."""
    frame = _parse_frame(bundle)
    header = frame.header
    slots = _slots(header)
    payload_info = _payload_info(header)
    payload_nonce = _required_b64(payload_info.get("nonce"), "payload.nonce", NONCE_BYTES)

    for slot in slots:
        current_slot_type = _slot_type(slot)
        if slot_type is not None and current_slot_type != slot_type:
            continue
        try:
            dek = _unwrap_slot(slot, secret, _kdf_params(header))
            payload = AESGCM(dek).decrypt(payload_nonce, frame.ciphertext, frame.header_bytes)
            return BundlePlaintext(payload=payload, slot_type=current_slot_type, header=header)
        except (InvalidTag, BundleFormatError):
            continue

    raise BundleAuthenticationError("bundle could not be opened with the provided secret")


@dataclass(frozen=True)
class _Frame:
    header: dict[str, Any]
    header_bytes: bytes
    ciphertext: bytes


def _parse_frame(bundle: bytes) -> _Frame:
    if len(bundle) < len(MAGIC) + HEADER_LEN_BYTES:
        raise BundleFormatError("bundle is too short")
    prefix = bundle[: len(MAGIC)]
    if prefix != MAGIC:
        raise BundleFormatError("bundle magic is invalid")

    header_len_start = len(MAGIC)
    header_len_end = header_len_start + HEADER_LEN_BYTES
    header_len = int.from_bytes(bundle[header_len_start:header_len_end], "big")
    if header_len > MAX_HEADER_LEN:
        raise BundleFormatError("bundle header is too large")
    if header_len == 0:
        raise BundleFormatError("bundle header is empty")

    header_start = header_len_end
    header_end = header_start + header_len
    if len(bundle) < header_end:
        raise BundleFormatError("bundle header is truncated")

    header_bytes = bundle[header_start:header_end]
    header = _parse_header(header_bytes)
    payload_info = _payload_info(header)
    ciphertext_length = _required_int(
        payload_info.get("ciphertext_length"), "payload.ciphertext_length"
    )
    if ciphertext_length < TAG_BYTES:
        raise BundleFormatError("payload ciphertext length is invalid")

    ciphertext = bundle[header_end:]
    if len(ciphertext) != ciphertext_length:
        raise BundleFormatError("bundle payload length does not match header")

    return _Frame(header=header, header_bytes=header_bytes, ciphertext=ciphertext)


def _parse_header(header_bytes: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleFormatError("bundle header is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BundleFormatError("bundle header must be a JSON object")
    _validate_header(parsed)
    return parsed


def _validate_header(header: Mapping[str, Any]) -> None:
    if header.get("magic") != MAGIC.decode("ascii"):
        raise BundleFormatError("bundle header magic is invalid")
    if header.get("format_schema") != FORMAT_SCHEMA:
        raise BundleFormatError("bundle format schema is unsupported")
    if header.get("cipher") != CIPHER:
        raise BundleFormatError("bundle cipher is unsupported")
    if header.get("kdf") != KDF:
        raise BundleFormatError("bundle KDF is unsupported")
    _kdf_params(header)
    _payload_info(header)
    _slots(header)


def _wrap_slot(
    slot_type: SlotType,
    secret_value: str | bytes,
    dek: bytes,
    random_bytes: Callable[[int], bytes],
) -> dict[str, str]:
    salt = _random_exact(random_bytes, SALT_BYTES)
    nonce = _random_exact(random_bytes, NONCE_BYTES)
    kek = _derive_kek(secret_value, salt, DEFAULT_KDF_PARAMS)
    wrapped_dek = AESGCM(kek).encrypt(nonce, dek, None)
    return {
        "nonce": _b64encode(nonce),
        "salt": _b64encode(salt),
        "type": slot_type,
        "wrapped_dek": _b64encode(wrapped_dek),
    }


def _unwrap_slot(
    slot: Mapping[str, Any],
    secret_value: str | bytes,
    kdf_params: KdfParams,
) -> bytes:
    salt = _required_b64(slot.get("salt"), "slot.salt", SALT_BYTES)
    nonce = _required_b64(slot.get("nonce"), "slot.nonce", NONCE_BYTES)
    wrapped_dek = _required_b64(slot.get("wrapped_dek"), "slot.wrapped_dek", DEK_BYTES + TAG_BYTES)
    kek = _derive_kek(secret_value, salt, kdf_params)
    dek = AESGCM(kek).decrypt(nonce, wrapped_dek, None)
    if len(dek) != DEK_BYTES:
        raise BundleFormatError("unwrapped DEK has invalid length")
    return dek


def _derive_kek(secret_value: str | bytes, salt: bytes, kdf_params: KdfParams) -> bytes:
    return hash_secret_raw(
        secret=_secret_bytes(secret_value),
        salt=salt,
        time_cost=kdf_params.time_cost,
        memory_cost=kdf_params.memory_cost,
        parallelism=kdf_params.parallelism,
        hash_len=KEK_BYTES,
        type=Type.ID,
    )


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    _reject_floats(value)
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _reject_floats(value: object) -> None:
    if isinstance(value, float):
        raise BundleFormatError("bundle header JSON must not contain floats")
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_floats(nested)


def _kdf_params(header: Mapping[str, Any]) -> KdfParams:
    raw_params = header.get("kdf_params")
    if not isinstance(raw_params, Mapping):
        raise BundleFormatError("bundle KDF params are missing")
    return KdfParams(
        time_cost=_required_int(raw_params.get("t"), "kdf_params.t"),
        memory_cost=_required_int(raw_params.get("m"), "kdf_params.m"),
        parallelism=_required_int(raw_params.get("p"), "kdf_params.p"),
    )


def _payload_info(header: Mapping[str, Any]) -> Mapping[str, Any]:
    payload_info = header.get("payload")
    if not isinstance(payload_info, Mapping):
        raise BundleFormatError("bundle payload metadata is missing")
    return payload_info


def _slots(header: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    slots = header.get("slots")
    if not isinstance(slots, list) or not slots:
        raise BundleFormatError("bundle has no unlock slots")
    for slot in slots:
        if not isinstance(slot, Mapping):
            raise BundleFormatError("bundle slot must be an object")
        _slot_type(slot)
    return slots


def _slot_type(slot: Mapping[str, Any]) -> SlotType:
    raw_slot_type = slot.get("type")
    if raw_slot_type == "passphrase" or raw_slot_type == "recovery":
        return raw_slot_type
    raise BundleFormatError("bundle slot type is unsupported")


def _required_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BundleFormatError(f"{field} must be an integer")
    if value <= 0:
        raise BundleFormatError(f"{field} must be positive")
    return value


def _required_b64(value: object, field: str, expected_length: int) -> bytes:
    if not isinstance(value, str):
        raise BundleFormatError(f"{field} must be base64 text")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise BundleFormatError(f"{field} is not valid base64") from exc
    if len(decoded) != expected_length:
        raise BundleFormatError(f"{field} has invalid length")
    return decoded


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _secret_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def _random_exact(random_bytes: Callable[[int], bytes], length: int) -> bytes:
    value = random_bytes(length)
    if len(value) != length:
        raise ValueError(f"random_bytes returned {len(value)} bytes; expected {length}")
    return value
