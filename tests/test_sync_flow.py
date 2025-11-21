"""Integration tests across snapshot -> planner -> executor pipeline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simple_sync import types
from simple_sync.engine import executor, planner, snapshot, state_store


def make_endpoint(root: Path, name: str) -> types.Endpoint:
    return types.Endpoint(id=name, type=types.EndpointType.LOCAL, path=str(root))


def make_entry(path: str, *, size: int, mtime: float) -> types.FileEntry:
    return types.FileEntry(path=path, is_dir=False, size=size, mtime=mtime)


def run_sync_once(
    profile: str,
    root_a: Path,
    root_b: Path,
    state: state_store.ProfileState,
) -> state_store.ProfileState:
    endpoint_a = make_endpoint(root_a, "A")
    endpoint_b = make_endpoint(root_b, "B")
    snap_a = snapshot.build_snapshot(root_a)
    snap_b = snapshot.build_snapshot(root_b)
    plan_input = planner.PlannerInput(
        profile=profile,
        snapshot_a=snap_a.entries,
        snapshot_b=snap_b.entries,
        endpoint_a=endpoint_a,
        endpoint_b=endpoint_b,
        state=state,
    )
    result = planner.plan(plan_input)
    if result.conflicts:
        raise AssertionError(f"Unexpected conflicts: {result.conflicts}")
    executor.apply_operations(result.operations)
    new_state = state_store.ProfileState(profile=profile)
    for entry in snapshot.build_snapshot(root_a).entries.values():
        state_store.record_entry(new_state, endpoint_a.id, entry)
    for entry in snapshot.build_snapshot(root_b).entries.values():
        state_store.record_entry(new_state, endpoint_b.id, entry)
    return new_state


class TestSyncFlow(unittest.TestCase):
    def test_new_file_is_copied(self):
        with tempfile.TemporaryDirectory() as a_tmp, tempfile.TemporaryDirectory() as b_tmp:
            root_a, root_b = Path(a_tmp), Path(b_tmp)
            (root_a / "file.txt").write_text("hello")
            state = state_store.ProfileState(profile="demo")
            state = run_sync_once("demo", root_a, root_b, state)
            self.assertTrue((root_b / "file.txt").exists())
            self.assertEqual(
                state_store.get_last_entry(state, "B", "file.txt").size,
                5,
            )

    def test_modified_file_propagates(self):
        with tempfile.TemporaryDirectory() as a_tmp, tempfile.TemporaryDirectory() as b_tmp:
            root_a, root_b = Path(a_tmp), Path(b_tmp)
            file_a = root_a / "file.txt"
            file_a.write_text("v1")
            state = state_store.ProfileState(profile="demo")
            state = run_sync_once("demo", root_a, root_b, state)

            file_a.write_text("v2-updated")
            state = run_sync_once("demo", root_a, root_b, state)
            self.assertEqual((root_b / "file.txt").read_text(), "v2-updated")

    def test_delete_removes_on_destination(self):
        with tempfile.TemporaryDirectory() as a_tmp, tempfile.TemporaryDirectory() as b_tmp:
            root_a, root_b = Path(a_tmp), Path(b_tmp)
            file_a = root_a / "obsolete.txt"
            file_a.write_text("content")
            state = state_store.ProfileState(profile="demo")
            state = run_sync_once("demo", root_a, root_b, state)
            file_a.unlink()
            state = run_sync_once("demo", root_a, root_b, state)
            self.assertFalse((root_b / "obsolete.txt").exists())

    def test_newest_policy_prefers_latest_mtime(self):
        with tempfile.TemporaryDirectory() as a_tmp, tempfile.TemporaryDirectory() as b_tmp:
            root_a, root_b = Path(a_tmp), Path(b_tmp)
            (root_a / "file.txt").write_text("A")
            (root_b / "file.txt").write_text("BB")
            state = state_store.ProfileState(profile="demo")
            state_store.record_entry(state, "A", make_entry("file.txt", size=1, mtime=1))
            state_store.record_entry(state, "B", make_entry("file.txt", size=1, mtime=1))
            endpoint_a = make_endpoint(root_a, "A")
            endpoint_b = make_endpoint(root_b, "B")
            snap_a = snapshot.build_snapshot(root_a)
            snap_b = snapshot.build_snapshot(root_b)
            plan_input = planner.PlannerInput(
                profile="demo",
                snapshot_a=snap_a.entries,
                snapshot_b=snap_b.entries,
                endpoint_a=endpoint_a,
                endpoint_b=endpoint_b,
                state=state,
                policy="newest",
            )
            plan_result = planner.plan(plan_input)
            self.assertEqual(len(plan_result.operations), 1)

    def test_prefer_policy_follows_configured_endpoint(self):
        with tempfile.TemporaryDirectory() as a_tmp, tempfile.TemporaryDirectory() as b_tmp:
            root_a, root_b = Path(a_tmp), Path(b_tmp)
            (root_a / "file.txt").write_text("A")
            (root_b / "file.txt").write_text("BB")
            state = state_store.ProfileState(profile="demo")
            state_store.record_entry(state, "A", make_entry("file.txt", size=1, mtime=1))
            state_store.record_entry(state, "B", make_entry("file.txt", size=1, mtime=1))
            endpoint_a = make_endpoint(root_a, "A")
            endpoint_b = make_endpoint(root_b, "B")
            snap_a = snapshot.build_snapshot(root_a)
            snap_b = snapshot.build_snapshot(root_b)
            plan_input = planner.PlannerInput(
                profile="demo",
                snapshot_a=snap_a.entries,
                snapshot_b=snap_b.entries,
                endpoint_a=endpoint_a,
                endpoint_b=endpoint_b,
                state=state,
                policy="prefer",
                prefer_endpoint="B",
            )
            plan_result = planner.plan(plan_input)
            self.assertEqual(len(plan_result.operations), 1)
            self.assertEqual(plan_result.operations[0].source.id, "B")

    def test_manual_policy_produces_conflict_records(self):
        with tempfile.TemporaryDirectory() as a_tmp, tempfile.TemporaryDirectory() as b_tmp:
            root_a, root_b = Path(a_tmp), Path(b_tmp)
            (root_a / "file.txt").write_text("A")
            (root_b / "file.txt").write_text("BB")
            state = state_store.ProfileState(profile="demo")
            state_store.record_entry(state, "A", make_entry("file.txt", size=1, mtime=1))
            state_store.record_entry(state, "B", make_entry("file.txt", size=1, mtime=1))
            endpoint_a = make_endpoint(root_a, "A")
            endpoint_b = make_endpoint(root_b, "B")
            snap_a = snapshot.build_snapshot(root_a)
            snap_b = snapshot.build_snapshot(root_b)
            plan_input = planner.PlannerInput(
                profile="demo",
                snapshot_a=snap_a.entries,
                snapshot_b=snap_b.entries,
                endpoint_a=endpoint_a,
                endpoint_b=endpoint_b,
                state=state,
                policy="manual",
                manual_behavior="copy_both",
            )
            plan_result = planner.plan(plan_input)
            self.assertEqual(len(plan_result.conflicts), 1)


if __name__ == "__main__":
    unittest.main()
