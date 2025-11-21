"""Helpers for executing remote commands with magic markers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .transport import SSHResult, run_ssh_command

BEGIN_MARKER = "__SS_BEGIN__"
END_MARKER = "__SS_END__"


@dataclass
class MarkerResult:
    exit_code: int
    body: str
    stderr: str


def wrap_remote_command(command: Sequence[str]) -> List[str]:
    """Inject marker printing around a command."""
    prefix = ["printf", f"{BEGIN_MARKER}\\n"]
    suffix = ["printf", f"{END_MARKER}\\n"]
    return ["sh", "-c", " ".join(_quote_segment(segment) for segment in [*prefix, *command, *suffix])]


def run_with_markers(
    *,
    host: str,
    remote_command: Sequence[str],
    ssh_command: Sequence[str] | str = "ssh",
    extra_args: Iterable[str] | None = None,
) -> MarkerResult:
    wrapped = wrap_remote_command(remote_command)
    ssh_result = run_ssh_command(host=host, remote_command=wrapped, ssh_command=ssh_command, extra_args=extra_args)
    return MarkerResult(
        exit_code=ssh_result.exit_code,
        body=_extract_between_markers(ssh_result.stdout),
        stderr=ssh_result.stderr,
    )


def _extract_between_markers(stdout: str) -> str:
    lines = stdout.splitlines()
    capturing = False
    body_lines: List[str] = []
    for line in lines:
        if not capturing:
            if line.strip() == BEGIN_MARKER:
                capturing = True
            continue
        if line.strip() == END_MARKER:
            break
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def _quote_segment(segment: str) -> str:
    return segment if segment.startswith("$") else f"'{segment}'"


__all__ = ["MarkerResult", "wrap_remote_command", "run_with_markers", "BEGIN_MARKER", "END_MARKER"]
