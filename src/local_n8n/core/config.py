from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from local_n8n.compose.template import DEFAULT_IMAGE_REF, InstanceConfig
from local_n8n.core.errors import UsageError

INSTANCE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def config_home() -> Path:
    override = os.environ.get("LOCAL_N8N_HOME")
    if override:
        return Path(override).expanduser()
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "local-n8n"
    return Path.home() / ".config" / "local-n8n"


def build_instance_config(
    instance_name: str,
    port: int = 5678,
    data_volume: str | None = None,
    image_ref: str = DEFAULT_IMAGE_REF,
    external_volume: bool = False,
) -> InstanceConfig:
    validate_instance_name(instance_name)
    return InstanceConfig(
        name=instance_name,
        port=port,
        instance_dir=config_home() / "instances" / instance_name,
        data_volume=data_volume,
        image_ref=image_ref,
        external_volume=external_volume,
    )


def validate_instance_name(instance_name: str) -> None:
    if INSTANCE_NAME_RE.fullmatch(instance_name):
        return

    raise UsageError(
        f"Invalid instance name: {instance_name!r}.",
        hint="Use lowercase letters, digits, and hyphens; start and end with a letter or digit.",
    )
