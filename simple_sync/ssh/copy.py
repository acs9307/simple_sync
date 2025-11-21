"""Remote copy helpers built on top of scp/ssh."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Sequence


class RemoteCopyError(RuntimeError):
    """Raised when SCP/SSH copy operations fail."""


def copy_local_to_remote(
    *,
    host: str,
    local_path: Path | str,
    remote_path: str,
    scp_command: Sequence[str] | str = "scp",
    extra_args: Iterable[str] | None = None,
) -> None:
    cmd = _build_scp_command(
        scp_command=scp_command,
        extra_args=extra_args,
        source=str(local_path),
        destination=f"{host}:{remote_path}",
    )
    _run_command(cmd)


def copy_remote_to_local(
    *,
    host: str,
    remote_path: str,
    local_path: Path | str,
    scp_command: Sequence[str] | str = "scp",
    extra_args: Iterable[str] | None = None,
) -> None:
    cmd = _build_scp_command(
        scp_command=scp_command,
        extra_args=extra_args,
        source=f"{host}:{remote_path}",
        destination=str(local_path),
    )
    _run_command(cmd)


def _build_scp_command(
    *,
    scp_command: Sequence[str] | str,
    extra_args: Iterable[str] | None,
    source: str,
    destination: str,
) -> list[str]:
    if isinstance(scp_command, str):
        base = [scp_command]
    else:
        base = list(scp_command)
    if not base:
        raise RemoteCopyError("scp_command must not be empty.")
    return base + list(extra_args or []) + [source, destination]


def _run_command(cmd: Sequence[str]) -> None:
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise RemoteCopyError(f"Failed to run command: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if _contains_prompt(stderr):
            raise RemoteCopyError("SSH authentication prompt detected; refusing to block.")
        raise RemoteCopyError(stderr or "scp command failed.")


def _contains_prompt(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in ["password:", "passphrase", "enter pin", "enter passcode"])


__all__ = ["RemoteCopyError", "copy_local_to_remote", "copy_remote_to_local"]
