"""Snapshot builder for local directories."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Sequence

from simple_sync import types


class SnapshotError(RuntimeError):
    """Raised when building a snapshot fails."""


@dataclass(frozen=True)
class SnapshotResult:
    root: Path
    entries: Dict[str, types.FileEntry]


def build_snapshot(
    root: Path | str,
    *,
    ignore_patterns: Sequence[str] | None = None,
) -> SnapshotResult:
    """Walk a directory tree and return metadata for each file/directory."""
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise SnapshotError(f"Snapshot root {base} does not exist.")
    if not base.is_dir():
        raise SnapshotError(f"Snapshot root {base} is not a directory.")

    entries: Dict[str, types.FileEntry] = {}
    resolved_ignore = tuple(ignore_patterns or [])

    for current_root, dirs, files in os.walk(base):
        current_path = Path(current_root)
        rel_dir = current_path.relative_to(base)
        rel_str = "." if str(rel_dir) == "." else rel_dir.as_posix()
        if rel_str != "." and _is_ignored(rel_str, resolved_ignore):
            dirs[:] = []
            continue
        if rel_str != ".":
            entries[rel_str] = _make_entry(current_path, rel_str, is_dir=True)

        dirs[:] = [d for d in dirs if not _is_ignored(_join_rel(rel_dir, d), resolved_ignore)]
        for name in files:
            rel_file = _join_rel(rel_dir, name)
            if _is_ignored(rel_file, resolved_ignore):
                continue
            file_path = current_path / name
            entries[rel_file] = _make_entry(file_path, rel_file, is_dir=False)

    return SnapshotResult(root=base, entries=entries)


def _join_rel(base: Path, child: str) -> str:
    if str(base) == ".":
        return child
    return Path(base, child).as_posix()


def _is_ignored(rel_path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in patterns)


def _make_entry(path: Path, rel_path: str, *, is_dir: bool) -> types.FileEntry:
    stat = path.stat()
    size = stat.st_size if not is_dir else 0
    return types.FileEntry(
        path=rel_path,
        is_dir=is_dir,
        size=size,
        mtime=stat.st_mtime,
    )


__all__ = ["SnapshotError", "SnapshotResult", "build_snapshot"]
