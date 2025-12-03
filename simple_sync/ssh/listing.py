"""Remote directory listing helpers."""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

from simple_sync import types
from .commands import MarkerResult, run_with_markers

FIND_FORMAT = "%P|%y|%s|%T@|%l\\n"


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
        parts = line.split("|", 4)
        if len(parts) < 4:
            continue
        rel_path, type_char, size_str, mtime_str, *rest = parts
        rel_path = rel_path or "."
        is_dir = type_char == "d"
        is_symlink = type_char == "l"
        size = 0 if (is_dir or is_symlink) else int(size_str)
        mtime = float(mtime_str)
        link_target = rest[0] if rest else None
        entry = types.FileEntry(
            path=rel_path,
            is_dir=is_dir,
            size=size,
            mtime=mtime,
            is_symlink=is_symlink,
            link_target=link_target or None,
        )
        entries[entry.path] = entry
    return entries


__all__ = ["RemoteListingError", "list_remote_entries"]
