"""Core synchronization data types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional, Tuple


class EndpointType(str, Enum):
    LOCAL = "local"
    SSH = "ssh"


@dataclass(frozen=True)
class Endpoint:
    """Represents either a local or SSH endpoint."""

    id: str
    type: EndpointType
    path: Path
    host: Optional[str] = None
    description: Optional[str] = None
    ssh_command: Optional[str] = None
    pre_connect_command: Optional[str] = None

    def __post_init__(self) -> None:
        normalized_path = Path(self.path).expanduser()
        object.__setattr__(self, "path", normalized_path)
        if self.type == EndpointType.SSH and not self.host:
            raise ValueError("SSH endpoints must include a host.")


@dataclass(frozen=True)
class FileEntry:
    """Filesystem entry metadata."""

    path: str
    is_dir: bool
    size: int
    mtime: float
    is_symlink: bool = False
    link_target: Optional[str] = None
    hash: Optional[str] = None

    def __post_init__(self) -> None:
        normalized = normalize_relative_path(self.path)
        object.__setattr__(self, "path", normalized)


class ChangeType(str, Enum):
    NEW = "new"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class OperationType(str, Enum):
    COPY = "copy"
    DELETE = "delete"
    MKDIR = "mkdir"
    MERGE = "merge"


@dataclass(frozen=True)
class Operation:
    """Operation to apply during synchronization."""

    type: OperationType
    path: str
    source: Optional[Endpoint] = None
    destination: Optional[Endpoint] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = normalize_relative_path(self.path)
        object.__setattr__(self, "path", normalized)


@dataclass(frozen=True)
class Conflict:
    """Describes a conflict requiring user input."""

    path: str
    endpoints: Tuple[Endpoint, Endpoint]
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = normalize_relative_path(self.path)
        object.__setattr__(self, "path", normalized)


def normalize_relative_path(path: str | Path) -> str:
    """Normalize a path relative to the endpoint root."""
    normalized_input = str(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:", normalized_input):
        raise ValueError(f"Absolute paths are not allowed: {path}")
    candidate = PurePosixPath(normalized_input)
    if candidate.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {path}")
    parts = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"Path escapes root: {path}")
        parts.append(part)
    return "/".join(parts) if parts else "."


__all__ = [
    "ChangeType",
    "Conflict",
    "Endpoint",
    "EndpointType",
    "FileEntry",
    "Operation",
    "OperationType",
    "normalize_relative_path",
]
