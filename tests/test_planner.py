"""Tests for the planner module."""

from __future__ import annotations

import unittest

from unittest import mock

from simple_sync.engine import planner, state_store
from simple_sync import types


def make_entry(path: str, *, size: int = 1, mtime: float = 1.0) -> types.FileEntry:
    return types.FileEntry(path=path, is_dir=False, size=size, mtime=mtime)


def make_endpoint(id_: str) -> types.Endpoint:
    return types.Endpoint(id=id_, type=types.EndpointType.LOCAL, path=f"/tmp/{id_}")


class TestPlanner(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint_a = make_endpoint("A")
        self.endpoint_b = make_endpoint("B")

    def _planner_input(self, snapshot_a, snapshot_b, state=None):
        return planner.PlannerInput(
            profile="demo",
            snapshot_a=snapshot_a,
            snapshot_b=snapshot_b,
            endpoint_a=self.endpoint_a,
            endpoint_b=self.endpoint_b,
            state=state or state_store.ProfileState(profile="demo"),
        )

    def test_new_file_on_a_copies_to_b(self):
        snap_a = {"file.txt": make_entry("file.txt")}
        snap_b = {}
        result = planner.plan(self._planner_input(snap_a, snap_b))
        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        self.assertEqual(op.source, self.endpoint_a)
        self.assertEqual(op.destination, self.endpoint_b)

    def test_both_modified_creates_conflict(self):
        snap_a = {"file.txt": make_entry("file.txt", size=2, mtime=5)}
        snap_b = {"file.txt": make_entry("file.txt", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.txt", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.txt", size=1, mtime=1))
        result = planner.plan(self._planner_input(snap_a, snap_b, state))
        self.assertEqual(len(result.conflicts), 0)
        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        self.assertEqual(op.metadata["reason"], "newest_wins")

    def test_both_modified_conflict_when_not_newest_policy(self):
        snap_a = {"file.txt": make_entry("file.txt", size=2, mtime=5)}
        snap_b = {"file.txt": make_entry("file.txt", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.txt", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.txt", size=1, mtime=1))
        result = planner.plan(
            planner.PlannerInput(
                profile="demo",
                snapshot_a=snap_a,
                snapshot_b=snap_b,
                endpoint_a=self.endpoint_a,
                endpoint_b=self.endpoint_b,
                state=state,
                policy="manual",
            )
        )
        self.assertEqual(len(result.conflicts), 1)

    def test_both_modified_prefer_policy(self):
        snap_a = {"file.txt": make_entry("file.txt", size=2, mtime=5)}
        snap_b = {"file.txt": make_entry("file.txt", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.txt", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.txt", size=1, mtime=1))
        result = planner.plan(
            planner.PlannerInput(
                profile="demo",
                snapshot_a=snap_a,
                snapshot_b=snap_b,
                endpoint_a=self.endpoint_a,
                endpoint_b=self.endpoint_b,
                state=state,
                policy="prefer",
                prefer_endpoint=self.endpoint_b.id,
            )
        )
        self.assertEqual(len(result.conflicts), 0)
        self.assertEqual(result.operations[0].source, self.endpoint_b)

    def test_manual_policy_copy_both(self):
        snap_a = {"file.txt": make_entry("file.txt", size=2, mtime=5)}
        snap_b = {"file.txt": make_entry("file.txt", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.txt", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.txt", size=1, mtime=1))
        with mock.patch("simple_sync.engine.planner.time.time", return_value=1700000000):
            result = planner.plan(
                planner.PlannerInput(
                    profile="demo",
                    snapshot_a=snap_a,
                    snapshot_b=snap_b,
                    endpoint_a=self.endpoint_a,
                    endpoint_b=self.endpoint_b,
                    state=state,
                    policy="manual",
                    manual_behavior="copy_both",
                )
            )
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(len(result.operations), 2)
        suffixes = {op.metadata["target_suffix"] for op in result.operations}
        self.assertIn("file.txt.conflict-A-1700000000", suffixes)
        self.assertIn("file.txt.conflict-B-1700000000", suffixes)
        self.assertEqual(result.conflicts[0].metadata.get("timestamp"), 1700000000)

    def test_delete_detected_when_missing_from_snapshots(self):
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("old.txt", size=1, mtime=1))
        result = planner.plan(self._planner_input({}, {}, state))
        delete_ops = [op for op in result.operations if op.type == types.OperationType.DELETE]
        self.assertEqual(len(delete_ops), 1)
        self.assertEqual(delete_ops[0].destination, self.endpoint_a)


if __name__ == "__main__":
    unittest.main()
