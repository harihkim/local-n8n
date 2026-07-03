from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LonError(Exception):
    message: str
    exit_code: int = 1
    hint: str | None = None


class UsageError(LonError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message=message, exit_code=2, hint=hint)


class PrerequisiteError(LonError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message=message, exit_code=10, hint=hint)


class PortInUseError(LonError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message=message, exit_code=11, hint=hint)


class InstanceNotFoundError(LonError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message=message, exit_code=13, hint=hint)


class FileWriteError(LonError):
    pass


class CommandFailedError(LonError):
    pass


class StartupTimeoutError(LonError):
    pass
