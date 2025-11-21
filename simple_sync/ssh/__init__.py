"""SSH helpers for simple_sync."""

from .commands import BEGIN_MARKER, END_MARKER, MarkerResult, run_with_markers, wrap_remote_command
from .copy import RemoteCopyError, copy_local_to_remote, copy_remote_to_local
from .listing import RemoteListingError, list_remote_entries
from .transport import SSHCommandError, SSHResult, run_ssh_command

__all__ = [
    "SSHCommandError",
    "SSHResult",
    "MarkerResult",
    "run_ssh_command",
    "run_with_markers",
    "wrap_remote_command",
    "BEGIN_MARKER",
    "END_MARKER",
    "RemoteListingError",
    "list_remote_entries",
    "RemoteCopyError",
    "copy_local_to_remote",
    "copy_remote_to_local",
]
