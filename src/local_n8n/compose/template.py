from __future__ import annotations

import base64
import os
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from local_n8n.core.errors import FileWriteError

DEFAULT_IMAGE_REF = "docker.n8n.io/n8nio/n8n"
LEGACY_DEFAULT_IMAGE_REFS = (
    "docker.n8n.io/n8nio/n8n:1.113.3"
    "@sha256:57f95a26b1b28527053fba6316d9d046395d9b4da9d0da486e838384a38fcf37",
)


@dataclass(frozen=True)
class InstanceConfig:
    name: str
    port: int
    instance_dir: Path
    data_volume: str | None = None
    image_ref: str = DEFAULT_IMAGE_REF

    @property
    def compose_path(self) -> Path:
        return self.instance_dir / "docker-compose.yml"

    @property
    def env_path(self) -> Path:
        return self.instance_dir / ".env"

    @property
    def project_name(self) -> str:
        return f"local-n8n-{self.name}"

    @property
    def volume_name(self) -> str:
        return self.data_volume or f"n8n_{self.name}_data"


def render_compose(config: InstanceConfig) -> str:
    return f"""services:
  n8n:
    image: {config.image_ref}
    restart: unless-stopped
    ports:
      - "${{N8N_PORT}}:${{N8N_PORT}}"
    env_file:
      - .env
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  n8n_data:
    name: {config.volume_name}
"""


def render_env(port: int, encryption_key: str, timezone: str) -> str:
    return "\n".join(
        [
            f"N8N_ENCRYPTION_KEY={encryption_key}",
            f"N8N_PORT={port}",
            "N8N_SECURE_COOKIE=false",
            "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true",
            "N8N_RUNNERS_ENABLED=true",
            f"GENERIC_TIMEZONE={timezone}",
            f"TZ={timezone}",
            "",
        ]
    )


def ensure_instance_files(config: InstanceConfig) -> None:
    try:
        config.instance_dir.mkdir(parents=True, exist_ok=True)
        config.compose_path.write_text(render_compose(config), encoding="utf-8")

        if not config.env_path.exists():
            config.env_path.write_text(
                render_env(
                    port=config.port,
                    encryption_key=generate_n8n_encryption_key(),
                    timezone=detect_timezone(),
                ),
                encoding="utf-8",
            )
            config.env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        raise FileWriteError(
            f"Could not write instance files under {config.instance_dir}.",
            hint=str(exc),
        ) from exc


def read_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        found_key, value = stripped.split("=", 1)
        if found_key == key:
            return value

    return None


def generate_n8n_encryption_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def detect_timezone() -> str:
    env_tz = os.environ.get("TZ")
    if env_tz:
        return env_tz

    if time.tzname[0]:
        return time.tzname[0]

    return "UTC"
