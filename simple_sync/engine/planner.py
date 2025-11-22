"""Planner: diff two snapshots and last state to produce operations/conflicts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from simple_sync import types
from simple_sync.engine import state_store


@dataclass
class PlannerInput:
    profile: str
    snapshot_a: Dict[str, types.FileEntry]
    snapshot_b: Dict[str, types.FileEntry]
    endpoint_a: types.Endpoint
    endpoint_b: types.Endpoint
    state: state_store.ProfileState
    policy: str = "newest"
    prefer_endpoint: str | None = None
    manual_behavior: str | None = None
    merge_text_files: bool = True
    merge_fallback: str = "newest"


@dataclass
class PlannerOutput:
    operations: List[types.Operation] = field(default_factory=list)
    conflicts: List[types.Conflict] = field(default_factory=list)


def plan(input_data: PlannerInput) -> PlannerOutput:
    """Compare current snapshots and last sync state, generating operations."""
    out = PlannerOutput()
    state_paths = set()
    for entries in input_data.state.endpoints.values():
        state_paths.update(entries.keys())
    all_paths = set(input_data.snapshot_a.keys()) | set(input_data.snapshot_b.keys()) | state_paths
    for path in sorted(all_paths):
        entry_a = input_data.snapshot_a.get(path)
        entry_b = input_data.snapshot_b.get(path)
        last_a = state_store.get_last_entry(input_data.state, input_data.endpoint_a.id, path)
        last_b = state_store.get_last_entry(input_data.state, input_data.endpoint_b.id, path)
        _classify_path(
            out,
            path,
            entry_a,
            entry_b,
            last_a,
            last_b,
            input_data.endpoint_a,
            input_data.endpoint_b,
            input_data.policy,
            input_data.prefer_endpoint,
            input_data.manual_behavior,
            input_data.merge_text_files,
            input_data.merge_fallback,
        )
    return out


def _classify_path(
    out: PlannerOutput,
    path: str,
    entry_a: types.FileEntry | None,
    entry_b: types.FileEntry | None,
    last_a: state_store.StoredEntry | None,
    last_b: state_store.StoredEntry | None,
    endpoint_a: types.Endpoint,
    endpoint_b: types.Endpoint,
    policy: str,
    prefer_endpoint: str | None,
    manual_behavior: str | None,
    merge_text_files: bool = True,
    merge_fallback: str = "newest",
) -> None:
    if entry_a and not entry_b:
        if _changed_since_last(entry_a, last_a) or last_b is None:
            out.operations.append(
                types.Operation(
                    type=types.OperationType.COPY,
                    path=path,
                    source=endpoint_a,
                    destination=endpoint_b,
                    metadata={"reason": "new_or_modified_on_a"},
                )
            )
        else:
            out.operations.append(
                types.Operation(
                    type=types.OperationType.DELETE,
                    path=path,
                    destination=endpoint_a,
                    metadata={"reason": "deleted_on_b"},
                )
            )
    elif entry_b and not entry_a:
        if _changed_since_last(entry_b, last_b) or last_a is None:
            out.operations.append(
                types.Operation(
                    type=types.OperationType.COPY,
                    path=path,
                    source=endpoint_b,
                    destination=endpoint_a,
                    metadata={"reason": "new_or_modified_on_b"},
                )
            )
        else:
            out.operations.append(
                types.Operation(
                    type=types.OperationType.DELETE,
                    path=path,
                    destination=endpoint_b,
                    metadata={"reason": "deleted_on_a"},
                )
            )
    elif entry_a and entry_b:
        if _entries_equal(entry_a, entry_b):
            return
        changed_a = _changed_since_last(entry_a, last_a)
        changed_b = _changed_since_last(entry_b, last_b)
        if changed_a and changed_b:
            # Check if we should attempt a merge for text files
            from simple_sync.engine import merge

            should_merge = (
                merge_text_files
                and not entry_a.is_dir
                and not entry_b.is_dir
                and merge.is_text_file(path)
                and last_a is not None
                and last_b is not None
            )

            if should_merge:
                # Attempt three-way merge
                out.operations.append(
                    types.Operation(
                        type=types.OperationType.MERGE,
                        path=path,
                        source=endpoint_a,
                        destination=endpoint_b,
                        metadata={
                            "reason": "merge_attempt",
                            "fallback_policy": merge_fallback,
                            "fallback_prefer": prefer_endpoint,
                            "fallback_manual_behavior": manual_behavior,
                        },
                    )
                )
            elif policy == "newest":
                winner, loser = _choose_newest(entry_a, entry_b, endpoint_a, endpoint_b)
                out.operations.append(
                    types.Operation(
                        type=types.OperationType.COPY,
                        path=path,
                        source=winner,
                        destination=loser,
                        metadata={"reason": "newest_wins"},
                    )
                )
            elif policy == "prefer" and prefer_endpoint:
                winner, loser = _choose_preferred(prefer_endpoint, endpoint_a, endpoint_b)
                out.operations.append(
                    types.Operation(
                        type=types.OperationType.COPY,
                        path=path,
                        source=winner,
                        destination=loser,
                        metadata={"reason": "prefer_policy"},
                    )
                )
            elif policy == "manual" and manual_behavior == "copy_both":
                timestamp = int(time.time())
                out.operations.extend(
                    _copy_both_operations(path, endpoint_a, endpoint_b, entry_a, entry_b, timestamp=timestamp)
                )
                out.conflicts.append(
                    types.Conflict(
                        path=path,
                        endpoints=(endpoint_a, endpoint_b),
                        reason="manual_copy_both",
                        metadata={"resolution": "copy_both", "timestamp": timestamp},
                    )
                )
            else:
                out.conflicts.append(
                    types.Conflict(
                        path=path,
                        endpoints=(endpoint_a, endpoint_b),
                        reason="both_modified",
                        metadata={"a": entry_a, "b": entry_b},
                    )
                )
        elif _changed_since_last(entry_a, last_a):
            out.operations.append(
                types.Operation(
                    type=types.OperationType.COPY,
                    path=path,
                    source=endpoint_a,
                    destination=endpoint_b,
                    metadata={"reason": "modified_on_a"},
                )
            )
        elif _changed_since_last(entry_b, last_b):
            out.operations.append(
                types.Operation(
                    type=types.OperationType.COPY,
                    path=path,
                    source=endpoint_b,
                    destination=endpoint_a,
                    metadata={"reason": "modified_on_b"},
                )
            )
    else:
        # Both missing currently; treat as delete if previously existed.
        if last_a:
            out.operations.append(
                types.Operation(
                    type=types.OperationType.DELETE,
                    path=path,
                    destination=endpoint_a,
                    metadata={"reason": "deleted_on_a"},
                )
            )
        if last_b:
            out.operations.append(
                types.Operation(
                    type=types.OperationType.DELETE,
                    path=path,
                    destination=endpoint_b,
                    metadata={"reason": "deleted_on_b"},
                )
            )


def _entries_equal(a: types.FileEntry, b: types.FileEntry) -> bool:
    return (a.is_dir == b.is_dir) and (a.size == b.size) and (int(a.mtime) == int(b.mtime))


def _changed_since_last(entry: types.FileEntry, last: state_store.StoredEntry | None) -> bool:
    if last is None:
        return True
    if entry.is_dir != last.is_dir:
        return True
    if entry.size != last.size:
        return True
    if int(entry.mtime) != int(last.mtime):
        return True
    return False


def _choose_newest(
    entry_a: types.FileEntry,
    entry_b: types.FileEntry,
    endpoint_a: types.Endpoint,
    endpoint_b: types.Endpoint,
) -> tuple[types.Endpoint, types.Endpoint]:
    if entry_a.mtime >= entry_b.mtime:
        return endpoint_a, endpoint_b
    return endpoint_b, endpoint_a


def _choose_preferred(
    prefer_endpoint: str,
    endpoint_a: types.Endpoint,
    endpoint_b: types.Endpoint,
) -> tuple[types.Endpoint, types.Endpoint]:
    if endpoint_a.id == prefer_endpoint:
        return endpoint_a, endpoint_b
    if endpoint_b.id == prefer_endpoint:
        return endpoint_b, endpoint_a
    return endpoint_a, endpoint_b


def _copy_both_operations(
    path: str,
    endpoint_a: types.Endpoint,
    endpoint_b: types.Endpoint,
    entry_a: types.FileEntry,
    entry_b: types.FileEntry,
    *,
    timestamp: int | None = None,
) -> List[types.Operation]:
    operations: List[types.Operation] = []
    timestamp = timestamp or int(time.time())
    suffix_a = f"{path}.conflict-{endpoint_a.id}-{timestamp}"
    suffix_b = f"{path}.conflict-{endpoint_b.id}-{timestamp}"
    operations.append(
        types.Operation(
            type=types.OperationType.COPY,
            path=path,
            source=endpoint_a,
            destination=endpoint_b,
            metadata={"reason": "manual_copy_both_copy", "target_suffix": suffix_a},
        )
    )
    operations.append(
        types.Operation(
            type=types.OperationType.COPY,
            path=path,
            source=endpoint_b,
            destination=endpoint_a,
            metadata={"reason": "manual_copy_both_copy", "target_suffix": suffix_b},
        )
    )
    return operations


__all__ = ["PlannerInput", "PlannerOutput", "plan"]
