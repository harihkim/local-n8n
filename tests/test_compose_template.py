from __future__ import annotations

import base64
import stat

from local_n8n.compose.template import (
    InstanceConfig,
    ensure_instance_files,
    generate_n8n_encryption_key,
    render_compose,
    render_env,
)


def test_generate_n8n_encryption_key_is_32_random_bytes_base64() -> None:
    decoded = base64.b64decode(generate_n8n_encryption_key())

    assert len(decoded) == 32


def test_render_compose_uses_explicit_volume_and_n8n_env_file(tmp_path) -> None:
    config = InstanceConfig(name="default", port=5678, instance_dir=tmp_path)

    rendered = render_compose(config)

    assert "image: docker.n8n.io/n8nio/n8n:" in rendered
    assert '      - "${N8N_PORT}:${N8N_PORT}"' in rendered
    assert "env_file:" in rendered
    assert "name: n8n_default_data" in rendered


def test_render_env_includes_phase_zero_n8n_settings() -> None:
    rendered = render_env(port=5678, encryption_key="secret", timezone="UTC")

    assert "N8N_ENCRYPTION_KEY=secret" in rendered
    assert "N8N_PORT=5678" in rendered
    assert "N8N_SECURE_COOKIE=false" in rendered
    assert "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true" in rendered
    assert "N8N_RUNNERS_ENABLED=true" in rendered
    assert "GENERIC_TIMEZONE=UTC" in rendered
    assert "TZ=UTC" in rendered


def test_ensure_instance_files_preserves_existing_env_key(tmp_path) -> None:
    config = InstanceConfig(name="default", port=5678, instance_dir=tmp_path)
    config.env_path.write_text("N8N_ENCRYPTION_KEY=keep-me\n", encoding="utf-8")

    ensure_instance_files(config)

    assert config.compose_path.exists()
    assert config.env_path.read_text(encoding="utf-8") == "N8N_ENCRYPTION_KEY=keep-me\n"


def test_ensure_instance_files_creates_env_mode_0600(tmp_path) -> None:
    config = InstanceConfig(name="default", port=5678, instance_dir=tmp_path)

    ensure_instance_files(config)

    mode = stat.S_IMODE(config.env_path.stat().st_mode)
    assert mode == 0o600
