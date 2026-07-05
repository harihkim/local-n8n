from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from local_n8n.core.crypto import (
    BundleAuthenticationError,
    BundleFormatError,
    open_bundle,
    seal_bundle,
)


class DeterministicRandom:
    def __init__(self) -> None:
        self._next = 0

    def __call__(self, length: int) -> bytes:
        value = bytes((self._next + offset) % 256 for offset in range(length))
        self._next += length
        return value


def test_seal_and_open_bundle_with_passphrase() -> None:
    bundle = _sealed_bundle()

    opened = open_bundle(bundle, secret="correct horse battery staple", slot_type="passphrase")

    assert opened.payload == b"portable n8n payload"
    assert opened.slot_type == "passphrase"
    assert opened.header["magic"] == "N8NB"


def test_recovery_code_opens_bundle() -> None:
    bundle = _sealed_bundle()

    opened = open_bundle(bundle, secret="recovery-code-1234", slot_type="recovery")

    assert opened.payload == b"portable n8n payload"
    assert opened.slot_type == "recovery"


def test_open_bundle_can_try_all_slots() -> None:
    bundle = _sealed_bundle()

    opened = open_bundle(bundle, secret="recovery-code-1234")

    assert opened.payload == b"portable n8n payload"
    assert opened.slot_type == "recovery"


def test_wrong_passphrase_fails() -> None:
    bundle = _sealed_bundle()

    with pytest.raises(BundleAuthenticationError):
        open_bundle(bundle, secret="wrong", slot_type="passphrase")


def test_header_tamper_fails_authentication() -> None:
    bundle = _sealed_bundle()
    header = _header(bundle)
    payload_nonce = header["payload"]["nonce"]
    assert isinstance(payload_nonce, str)
    replacement = "A" if payload_nonce[0] != "A" else "B"
    header["payload"]["nonce"] = replacement + payload_nonce[1:]
    tampered = _replace_header(bundle, header)

    with pytest.raises(BundleAuthenticationError):
        open_bundle(tampered, secret="correct horse battery staple")


def test_bad_magic_is_rejected() -> None:
    bundle = bytearray(_sealed_bundle())
    bundle[0:4] = b"NOPE"

    with pytest.raises(BundleFormatError):
        open_bundle(bytes(bundle), secret="correct horse battery staple")


def test_header_magic_mismatch_is_rejected() -> None:
    bundle = _sealed_bundle()
    header = _header(bundle)
    header["magic"] = "NOPE"
    tampered = _replace_header(bundle, header)

    with pytest.raises(BundleFormatError):
        open_bundle(tampered, secret="correct horse battery staple")


def test_unknown_format_schema_is_rejected() -> None:
    bundle = _sealed_bundle()
    header = _header(bundle)
    header["format_schema"] = 999
    tampered = _replace_header(bundle, header)

    with pytest.raises(BundleFormatError):
        open_bundle(tampered, secret="correct horse battery staple")


def test_trailing_bytes_are_rejected() -> None:
    bundle = _sealed_bundle() + b"extra"

    with pytest.raises(BundleFormatError):
        open_bundle(bundle, secret="correct horse battery staple")


def test_deterministic_known_answer_vector() -> None:
    bundle = _sealed_bundle()

    assert (
        hashlib.sha256(bundle).hexdigest()
        == "2d9fbc674dfc7d04bc2f48c955f32da99e1a09fe8e24e02a9c2bf75c84a6661f"
    )


def test_empty_payload_is_rejected() -> None:
    with pytest.raises(ValueError):
        seal_bundle(
            b"",
            passphrase="correct horse battery staple",
            recovery_code="recovery-code-1234",
            random_bytes=DeterministicRandom(),
        )


def _sealed_bundle() -> bytes:
    return seal_bundle(
        b"portable n8n payload",
        passphrase="correct horse battery staple",
        recovery_code="recovery-code-1234",
        random_bytes=DeterministicRandom(),
    )


def _header(bundle: bytes) -> dict[str, Any]:
    header_length = int.from_bytes(bundle[4:8], "big")
    header_bytes = bundle[8 : 8 + header_length]
    parsed = json.loads(header_bytes.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _replace_header(bundle: bytes, header: dict[str, Any]) -> bytes:
    old_header_length = int.from_bytes(bundle[4:8], "big")
    payload = bundle[8 + old_header_length :]
    header_bytes = _canonical_test_json(header)
    return b"N8NB" + len(header_bytes).to_bytes(4, "big") + header_bytes + payload


def _canonical_test_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
