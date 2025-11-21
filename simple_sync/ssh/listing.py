"""Remote directory listing helpers."""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

from simple_sync import types
from .commands import MarkerResult, run_with_markers

FIND_FORMAT = "%P|%y|%s|%T@\\n"


class RemoteListingError(RuntimeError):
    """Raised when remote listing fails."""


def list_remote_entries(
    *,
    host: str,
    root: str,
    ssh_command: Sequence[str] | str = "ssh",
    extra_args: Iterable[str] | None = None,
) -> Dict[str, types.FileEntry]:
    """List files under root on a remote host."""
    remote_command = ["find", root, "-printf", FIND_FORMAT]
    result = run_with_markers(
        host=host,
        remote_command=remote_command,
        ssh_command=ssh_command,
        extra_args=extra_args,
    )
    if result.exit_code != 0:
        raise RemoteListingError(f"Remote find failed: {result.stderr.strip()}")
    entries: Dict[str, types.FileEntry] = {}
    for line in result.body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rel_path, type_char, size_str, mtime_str = line.split("|", 3)
        except ValueError:
            continue
        rel_path = rel_path or "."
        is_dir = type_char == "d"
        size = int(size_str) if not is_dir else 0
        mtime = float(mtime_str)
        entry = types.FileEntry(path=rel_path, is_dir=is_dir, size=size, mtime=mtime)
        entries[entry.path] = entry
    return entries


__all__ = ["RemoteListingError", "list_remote_entries"]
