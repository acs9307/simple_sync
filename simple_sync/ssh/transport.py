"""Utilities for executing SSH commands."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Sequence


class SSHCommandError(RuntimeError):
    """Raised when an SSH command cannot be executed."""


@dataclass
class SSHResult:
    exit_code: int
    stdout: str
    stderr: str
    auth_failed: bool = False
    prompt_detected: bool = False


def run_ssh_command(
    *,
    host: str,
    remote_command: Sequence[str],
    ssh_command: Sequence[str] | str = "ssh",
    extra_args: Iterable[str] | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> SSHResult:
    """Execute a remote command via SSH and capture its output."""
    if isinstance(ssh_command, str):
        base_cmd: List[str] = [ssh_command]
    else:
        base_cmd = list(ssh_command)
    if not base_cmd:
        raise SSHCommandError("ssh_command must not be empty.")
    cmd = base_cmd + list(extra_args or []) + [host, _quote_remote_command(remote_command)]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - system failures
        raise SSHCommandError(f"Failed to execute SSH command: {exc}") from exc
    stderr = completed.stderr
    auth_failed = _contains_auth_failure(stderr)
    prompt_detected = _contains_prompt(stderr)
    return SSHResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=stderr,
        auth_failed=auth_failed,
        prompt_detected=prompt_detected,
    )


def _contains_auth_failure(stderr: str) -> bool:
    lowered = stderr.lower()
    return "permission denied" in lowered or "authentication failed" in lowered


def _contains_prompt(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in ["password:", "passphrase", "enter pin", "enter passcode"])


def _quote_remote_command(parts: Sequence[str]) -> str:
    if not parts:
        return ""
    return " ".join(shlex.quote(part) for part in parts)


__all__ = ["SSHCommandError", "SSHResult", "run_ssh_command"]
