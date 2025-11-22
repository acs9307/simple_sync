"""Executor for applying planned local sync operations."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

from simple_sync import types
from simple_sync.engine import merge, state_store
from simple_sync.ssh import copy as ssh_copy
from simple_sync.ssh import transport as ssh_transport

logger = logging.getLogger(__name__)


class ExecutionError(RuntimeError):
    """Raised when applying operations fails."""


def apply_operations(
    ops: Iterable[types.Operation],
    *,
    dry_run: bool = False,
    state: Optional[state_store.ProfileState] = None
) -> None:
    """Apply a list of operations to the filesystem."""
    for op in ops:
        if op.type == types.OperationType.COPY:
            _copy(op, dry_run=dry_run)
        elif op.type == types.OperationType.DELETE:
            _delete(op, dry_run=dry_run)
        elif op.type == types.OperationType.MKDIR:
            _mkdir(op, dry_run=dry_run)
        elif op.type == types.OperationType.MERGE:
            _merge(op, dry_run=dry_run, state=state)
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


def _merge(
    op: types.Operation,
    *,
    dry_run: bool,
    state: Optional[state_store.ProfileState] = None
) -> None:
    """Attempt to merge two text files, falling back to configured policy on failure."""
    if not op.source or not op.destination:
        raise ExecutionError("MERGE operation requires source and destination endpoints.")

    logger.info("Attempting to merge %s", op.path)

    if dry_run:
        logger.info("Dry-run: Would attempt merge for %s", op.path)
        return

    # Get file contents from both endpoints
    src_root = Path(op.source.path)
    dst_root = Path(op.destination.path)

    try:
        content_a = _read_file_content(op.source, src_root, op.path)
        content_b = _read_file_content(op.destination, dst_root, op.path)
    except Exception as exc:
        logger.warning("Failed to read files for merge: %s. Falling back.", exc)
        _apply_fallback(op)
        return

    # Check if files are actually text
    if merge.is_binary_content(content_a.encode('utf-8', errors='ignore')) or \
       merge.is_binary_content(content_b.encode('utf-8', errors='ignore')):
        logger.warning("Binary content detected for %s. Falling back.", op.path)
        _apply_fallback(op)
        return

    # Get base content from state if available
    base_content = None
    if state:
        # For now, we don't have base content stored, so we'll attempt a simple merge
        # In the future, we could enhance the state store to keep text file contents
        pass

    # Attempt merge
    if base_content:
        # Three-way merge
        merge_result = merge.merge_three_way(base_content, content_a, content_b)
    else:
        # Without base content, try a simple two-way merge
        # This will work if changes don't overlap
        logger.info("No base content available, attempting simple merge for %s", op.path)
        merge_result = _simple_two_way_merge(content_a, content_b)

    if merge_result.success and merge_result.content:
        logger.info("Successfully merged %s", op.path)
        # Write merged content to both endpoints
        try:
            _write_file_content(op.source, src_root, op.path, merge_result.content)
            _write_file_content(op.destination, dst_root, op.path, merge_result.content)
        except Exception as exc:
            raise ExecutionError(f"Failed to write merged content: {exc}") from exc
    else:
        logger.warning("Merge failed for %s: %s. Falling back.", op.path, merge_result.conflicts)
        _apply_fallback(op)


def _simple_two_way_merge(content_a: str, content_b: str) -> merge.MergeResult:
    """
    Attempt a simple merge without base content.

    This uses an empty string as the base, which works if both sides
    only added lines or made non-overlapping changes.
    """
    # Use empty base for simple case
    return merge.merge_three_way("", content_a, content_b)


def _read_file_content(endpoint: types.Endpoint, root: Path, path: str) -> str:
    """Read file content from an endpoint."""
    if endpoint.type == types.EndpointType.LOCAL:
        file_path = root / path
        return file_path.read_text(encoding='utf-8')
    else:
        # SSH endpoint
        remote_path = _remote_path(root, path)
        result = ssh_transport.run_ssh_command(
            host=_require_host(endpoint),
            remote_command=["cat", remote_path],
            ssh_command=endpoint.ssh_command or "ssh",
        )
        if result.exit_code != 0:
            raise ExecutionError(f"Failed to read remote file: {result.stderr}")
        return result.stdout


def _write_file_content(endpoint: types.Endpoint, root: Path, path: str, content: str) -> None:
    """Write file content to an endpoint."""
    if endpoint.type == types.EndpointType.LOCAL:
        file_path = root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
    else:
        # SSH endpoint - write to temp file then copy
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            remote_path = _remote_path(root, path)
            ssh_copy.copy_local_to_remote(
                host=_require_host(endpoint),
                local_path=Path(tmp_path),
                remote_path=remote_path,
                scp_command=endpoint.ssh_command or "scp",
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def _apply_fallback(op: types.Operation) -> None:
    """Apply fallback policy when merge fails."""
    fallback_policy = op.metadata.get("fallback_policy", "newest")
    logger.info("Applying fallback policy '%s' for %s", fallback_policy, op.path)

    if fallback_policy == "newest":
        # Use newest wins - we'd need to know which is newer
        # For now, prefer source (endpoint A)
        fallback_op = types.Operation(
            type=types.OperationType.COPY,
            path=op.path,
            source=op.source,
            destination=op.destination,
            metadata={"reason": "merge_fallback_newest"},
        )
        _copy(fallback_op, dry_run=False)
    elif fallback_policy == "manual":
        # Create conflict copies
        manual_behavior = op.metadata.get("fallback_manual_behavior", "copy_both")
        if manual_behavior == "copy_both":
            logger.error("Manual resolution required for %s - please resolve manually", op.path)
            raise ExecutionError(f"Manual resolution required for {op.path}")
        else:
            raise ExecutionError(f"Merge failed and manual policy not configured for {op.path}")
    else:
        # Default to copying from source
        fallback_op = types.Operation(
            type=types.OperationType.COPY,
            path=op.path,
            source=op.source,
            destination=op.destination,
            metadata={"reason": "merge_fallback_default"},
        )
        _copy(fallback_op, dry_run=False)


__all__ = ["ExecutionError", "apply_operations"]
