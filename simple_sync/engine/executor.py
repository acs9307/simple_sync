"""Executor for applying planned local sync operations."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from simple_sync import types
from simple_sync.ssh import copy as ssh_copy
from simple_sync.ssh import transport as ssh_transport


class ExecutionError(RuntimeError):
    """Raised when applying operations fails."""


def apply_operations(ops: Iterable[types.Operation], *, dry_run: bool = False) -> None:
    """Apply a list of operations to the filesystem."""
    for op in ops:
        if op.type == types.OperationType.COPY:
            _copy(op, dry_run=dry_run)
        elif op.type == types.OperationType.DELETE:
            _delete(op, dry_run=dry_run)
        elif op.type == types.OperationType.MKDIR:
            _mkdir(op, dry_run=dry_run)
        else:  # pragma: no cover - unknown ops future-proofing
            raise ExecutionError(f"Unsupported operation type: {op.type}")


def _copy(op: types.Operation, *, dry_run: bool) -> None:
    if not op.source or not op.destination:
        raise ExecutionError("COPY operation requires source and destination endpoints.")
    src_root = Path(op.source.path)
    dst_root = Path(op.destination.path)
    target_suffix = op.metadata.get("target_suffix") if op.metadata else None
    rel_path = target_suffix or op.path

    if op.source.type == types.EndpointType.LOCAL and op.destination.type == types.EndpointType.LOCAL:
        src_path = src_root / op.path
        dst_path = dst_root / rel_path
        if dry_run:
            return
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            shutil.copy2(src_path, dst_path)
    elif op.source.type == types.EndpointType.LOCAL and op.destination.type == types.EndpointType.SSH:
        if dry_run:
            return
        remote_target = _remote_path(dst_root, rel_path)
        try:
            ssh_copy.copy_local_to_remote(
                host=_require_host(op.destination),
                local_path=src_root / op.path,
                remote_path=remote_target,
                scp_command=op.destination.ssh_command or "scp",
            )
        except ssh_copy.RemoteCopyError as exc:
            raise ExecutionError(str(exc)) from exc
    elif op.source.type == types.EndpointType.SSH and op.destination.type == types.EndpointType.LOCAL:
        if dry_run:
            return
        remote_source = _remote_path(src_root, op.path)
        try:
            ssh_copy.copy_remote_to_local(
                host=_require_host(op.source),
                remote_path=remote_source,
                local_path=dst_root / rel_path,
                scp_command=op.source.ssh_command or "scp",
            )
        except ssh_copy.RemoteCopyError as exc:
            raise ExecutionError(str(exc)) from exc
    else:
        if dry_run:
            return
        _relay_remote_copy(
            source=op.source,
            destination=op.destination,
            path=rel_path,
        )


def _delete(op: types.Operation, *, dry_run: bool) -> None:
    if not op.destination:
        raise ExecutionError("DELETE operation requires destination endpoint.")
    dst_root = Path(op.destination.path)
    if op.destination.type == types.EndpointType.LOCAL:
        target = dst_root / op.path
        if dry_run or not target.exists():
            return
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    elif op.destination.type == types.EndpointType.SSH:
        if dry_run:
            return
        remote_target = _remote_path(dst_root, op.path)
        result = ssh_transport.run_ssh_command(
            host=_require_host(op.destination),
            remote_command=["rm", "-rf", remote_target],
            ssh_command=op.destination.ssh_command or "ssh",
        )
        if result.exit_code != 0:
            message = result.stderr.strip() or "Remote delete failed."
            if result.prompt_detected or result.auth_failed:
                message = "SSH authentication prompt detected; refusing to continue."
            raise ExecutionError(message)
    else:
        raise ExecutionError("Unsupported destination endpoint for delete.")


def _mkdir(op: types.Operation, *, dry_run: bool) -> None:
    if not op.destination:
        raise ExecutionError("MKDIR operation requires destination endpoint.")
    dst_root = Path(op.destination.path)
    if dry_run:
        return
    (dst_root / op.path).mkdir(parents=True, exist_ok=True)


def _remote_path(root: Path, rel_path: str) -> str:
    return str(PurePosixPath(str(root)) / rel_path)


def _require_host(endpoint: types.Endpoint) -> str:
    if not endpoint.host:
        raise ExecutionError(f"Endpoint '{endpoint.id}' is missing host information.")
    return endpoint.host


def _relay_remote_copy(*, source: types.Endpoint, destination: types.Endpoint, path: str) -> None:
    local_tmp = Path(tempfile.mkdtemp(prefix="simple_sync_relay"))
    try:
        temp_file = local_tmp / Path(path).name
        ssh_copy.copy_remote_to_local(
            host=_require_host(source),
            remote_path=_remote_path(Path(source.path), path),
            local_path=temp_file,
            scp_command=source.ssh_command or "scp",
        )
        ssh_copy.copy_local_to_remote(
            host=_require_host(destination),
            local_path=temp_file,
            remote_path=_remote_path(Path(destination.path), path),
            scp_command=destination.ssh_command or "scp",
        )
    except ssh_copy.RemoteCopyError as exc:
        raise ExecutionError(str(exc)) from exc
    finally:
        shutil.rmtree(local_tmp, ignore_errors=True)


__all__ = ["ExecutionError", "apply_operations"]
