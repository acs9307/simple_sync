"""Persistent profile state store."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from simple_sync import config, types

STATE_VERSION = 4


class StateStoreError(RuntimeError):
    """Raised when state files cannot be read or parsed."""


@dataclass
class StoredEntry:
    """Metadata persisted for each file in the last sync."""

    path: str
    is_dir: bool
    size: int
    mtime: float
    is_symlink: bool = False
    link_target: Optional[str] = None
    hash: Optional[str] = None


@dataclass
class ConflictRecord:
    path: str
    reason: str
    endpoints: tuple[str, str]
    timestamp: float
    resolution: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class ProfileState:
    profile: str
    endpoints: Dict[str, Dict[str, StoredEntry]] = field(default_factory=dict)
    conflicts: List[ConflictRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": STATE_VERSION,
            "profile": self.profile,
            "endpoints": {
                endpoint: {path: asdict(entry) for path, entry in entries.items()}
                for endpoint, entries in self.endpoints.items()
            },
            "conflicts": [
                {
                    "path": conflict.path,
                    "reason": conflict.reason,
                    "endpoints": list(conflict.endpoints),
                    "timestamp": conflict.timestamp,
                    "resolution": conflict.resolution,
                    "metadata": conflict.metadata,
                }
                for conflict in self.conflicts
            ],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "ProfileState":
        version = payload.get("version", 1)
        if version not in {1, 2, 3, STATE_VERSION}:
            raise StateStoreError("Unsupported state file version.")
        profile = payload.get("profile")
        if not isinstance(profile, str):
            raise StateStoreError("State file missing 'profile' field.")
        endpoints_data = payload.get("endpoints", {})
        endpoints: Dict[str, Dict[str, StoredEntry]] = {}
        if isinstance(endpoints_data, dict):
            for endpoint_id, entries in endpoints_data.items():
                endpoint_entries: Dict[str, StoredEntry] = {}
                if isinstance(entries, dict):
                    for path, entry_data in entries.items():
                        if not isinstance(entry_data, dict):
                            continue
                        endpoint_entries[path] = StoredEntry(
                            path=entry_data.get("path", path),
                            is_dir=bool(entry_data.get("is_dir", False)),
                            size=int(entry_data.get("size", 0)),
                            mtime=float(entry_data.get("mtime", 0.0)),
                            is_symlink=bool(entry_data.get("is_symlink", False)),
                            link_target=entry_data.get("link_target"),
                            hash=entry_data.get("hash"),
                        )
                endpoints[endpoint_id] = endpoint_entries
        conflicts: List[ConflictRecord] = []
        if version >= 2:
            conflicts_data = payload.get("conflicts", [])
            if isinstance(conflicts_data, list):
                for record in conflicts_data:
                    if not isinstance(record, dict):
                        continue
                    endpoints_list = record.get("endpoints", [])
                    if not isinstance(endpoints_list, list) or len(endpoints_list) != 2:
                        continue
                    conflicts.append(
                        ConflictRecord(
                            path=str(record.get("path", "")),
                            reason=str(record.get("reason", "")),
                            endpoints=(str(endpoints_list[0]), str(endpoints_list[1])),
                            timestamp=float(record.get("timestamp", time.time())),
                            resolution=record.get("resolution"),
                            metadata=record.get("metadata", {}) or {},
                        )
                    )
        return cls(profile=profile, endpoints=endpoints, conflicts=conflicts)


def load_state(profile_name: str, base_dir: Path | None = None) -> ProfileState:
    """Load state for a profile; returns empty state if file is missing."""
    base = config.ensure_config_structure(base_dir)
    path = _state_path(base, profile_name)
    if not path.exists():
        return ProfileState(profile=profile_name)
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise StateStoreError(f"Failed to parse state file {path}: {exc}") from exc
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise StateStoreError(f"Unable to read state file {path}: {exc}") from exc
    return ProfileState.from_dict(payload)


def save_state(state: ProfileState, base_dir: Path | None = None) -> Path:
    """Persist profile state to the state/ directory."""
    base = config.ensure_config_structure(base_dir)
    path = _state_path(base, state.profile)
    data = json.dumps(state.to_dict(), indent=2, sort_keys=True)
    path.write_text(data + "\n")
    return path


def record_entry(
    state: ProfileState,
    endpoint_id: str,
    entry: types.FileEntry,
) -> None:
    """Store the metadata for a given endpoint/path combination."""
    normalized_path = entry.path
    state.endpoints.setdefault(endpoint_id, {})[normalized_path] = StoredEntry(
        path=normalized_path,
        is_dir=entry.is_dir,
        size=entry.size,
        mtime=entry.mtime,
        is_symlink=entry.is_symlink,
        link_target=entry.link_target,
        hash=entry.hash,
    )


def record_conflict(
    state: ProfileState,
    *,
    path: str,
    reason: str,
    endpoints: tuple[str, str],
    resolution: str | None = None,
    timestamp: float | None = None,
    metadata: Dict[str, object] | None = None,
) -> None:
    state.conflicts.append(
        ConflictRecord(
            path=path,
            reason=reason,
            endpoints=endpoints,
            timestamp=timestamp or time.time(),
            resolution=resolution,
            metadata=metadata or {},
        )
    )


def get_last_entry(
    state: ProfileState,
    endpoint_id: str,
    rel_path: str | Path,
) -> Optional[StoredEntry]:
    """Fetch the previously stored entry for an endpoint/path."""
    normalized = types.normalize_relative_path(rel_path)
    return state.endpoints.get(endpoint_id, {}).get(normalized)


def _state_path(base: Path, profile_name: str) -> Path:
    safe_name = profile_name.replace("/", "_")
    return base / "state" / f"{safe_name}.json"


__all__ = [
    "ProfileState",
    "StateStoreError",
    "StoredEntry",
    "ConflictRecord",
    "get_last_entry",
    "load_state",
    "record_conflict",
    "record_entry",
    "save_state",
]
