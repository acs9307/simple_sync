"""Tests for planner merge integration."""

from __future__ import annotations

import unittest

from simple_sync.engine import planner, state_store
from simple_sync import types


def make_entry(path: str, *, size: int = 1, mtime: float = 1.0, is_dir: bool = False) -> types.FileEntry:
    return types.FileEntry(path=path, is_dir=is_dir, size=size, mtime=mtime)


def make_endpoint(id_: str) -> types.Endpoint:
    return types.Endpoint(id=id_, type=types.EndpointType.LOCAL, path=f"/tmp/{id_}")


class TestPlannerMergeIntegration(unittest.TestCase):
    """Test that planner creates MERGE operations correctly."""

    def setUp(self) -> None:
        self.endpoint_a = make_endpoint("A")
        self.endpoint_b = make_endpoint("B")

    def _planner_input(
        self,
        snapshot_a,
        snapshot_b,
        state=None,
        policy="newest",
        merge_text_files=True,
        merge_fallback="newest",
        prefer_endpoint=None,
        manual_behavior=None,
    ):
        return planner.PlannerInput(
            profile="demo",
            snapshot_a=snapshot_a,
            snapshot_b=snapshot_b,
            endpoint_a=self.endpoint_a,
            endpoint_b=self.endpoint_b,
            state=state or state_store.ProfileState(profile="demo"),
            policy=policy,
            merge_text_files=merge_text_files,
            merge_fallback=merge_fallback,
            prefer_endpoint=prefer_endpoint,
            manual_behavior=manual_behavior,
        )

    def test_both_modified_text_file_creates_merge_operation(self):
        """Test that modified text files create MERGE operations."""
        snap_a = {"file.py": make_entry("file.py", size=2, mtime=5)}
        snap_b = {"file.py": make_entry("file.py", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.py", size=1, mtime=1))

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        self.assertEqual(len(result.operations), 1)
        self.assertEqual(len(result.conflicts), 0)
        op = result.operations[0]
        self.assertEqual(op.type, types.OperationType.MERGE)
        self.assertEqual(op.path, "file.py")
        self.assertEqual(op.metadata["reason"], "merge_attempt")
        self.assertEqual(op.metadata["fallback_policy"], "newest")

    def test_both_modified_non_text_file_uses_policy(self):
        """Test that non-text files don't trigger merge."""
        snap_a = {"image.png": make_entry("image.png", size=2, mtime=5)}
        snap_b = {"image.png": make_entry("image.png", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("image.png", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("image.png", size=1, mtime=1))

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        # Should use newest policy, not merge
        self.assertEqual(op.type, types.OperationType.COPY)
        self.assertEqual(op.metadata["reason"], "newest_wins")

    def test_merge_disabled_uses_policy(self):
        """Test that disabling merge uses regular policy."""
        snap_a = {"file.py": make_entry("file.py", size=2, mtime=5)}
        snap_b = {"file.py": make_entry("file.py", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.py", size=1, mtime=1))

        result = planner.plan(
            self._planner_input(snap_a, snap_b, state, merge_text_files=False)
        )

        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        self.assertEqual(op.type, types.OperationType.COPY)
        self.assertEqual(op.metadata["reason"], "newest_wins")

    def test_merge_with_different_fallback_policies(self):
        """Test that fallback policy is passed in metadata."""
        snap_a = {"file.py": make_entry("file.py", size=2, mtime=5)}
        snap_b = {"file.py": make_entry("file.py", size=3, mtime=6)}
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.py", size=1, mtime=1))

        result = planner.plan(
            self._planner_input(
                snap_a, snap_b, state, merge_fallback="manual", policy="manual", manual_behavior="copy_both"
            )
        )

        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        self.assertEqual(op.type, types.OperationType.MERGE)
        self.assertEqual(op.metadata["fallback_policy"], "manual")
        self.assertEqual(op.metadata["fallback_manual_behavior"], "copy_both")

    def test_directories_dont_trigger_merge(self):
        """Test that directories are not merged."""
        snap_a = {"dir": make_entry("dir", is_dir=True, size=0, mtime=5)}
        snap_b = {"dir": make_entry("dir", is_dir=True, size=0, mtime=5)}  # same mtime
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("dir", is_dir=True, size=0, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("dir", is_dir=True, size=0, mtime=1))

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        # Directories with same size and mtime should be ignored
        self.assertEqual(len(result.operations), 0)

    def test_merge_requires_state_entries(self):
        """Test that merge requires both files to exist in state."""
        snap_a = {"file.py": make_entry("file.py", size=2, mtime=5)}
        snap_b = {"file.py": make_entry("file.py", size=3, mtime=6)}
        # State has no entries (new file on both sides)
        state = state_store.ProfileState(profile="demo")

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        # Without state entries, can't do three-way merge
        # Should use policy instead
        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        self.assertEqual(op.type, types.OperationType.COPY)

    def test_only_one_side_modified_no_merge(self):
        """Test that only one side modified doesn't trigger merge."""
        snap_a = {"file.py": make_entry("file.py", size=2, mtime=5)}
        snap_b = {"file.py": make_entry("file.py", size=1, mtime=1)}  # unchanged
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.py", size=1, mtime=1))

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        self.assertEqual(len(result.operations), 1)
        op = result.operations[0]
        # Only A modified, should just copy
        self.assertEqual(op.type, types.OperationType.COPY)
        self.assertEqual(op.source, self.endpoint_a)
        self.assertEqual(op.destination, self.endpoint_b)

    def test_multiple_text_files_get_merge_operations(self):
        """Test that multiple modified text files each get merge operations."""
        snap_a = {
            "file1.py": make_entry("file1.py", size=2, mtime=5),
            "file2.js": make_entry("file2.js", size=2, mtime=5),
        }
        snap_b = {
            "file1.py": make_entry("file1.py", size=3, mtime=6),
            "file2.js": make_entry("file2.js", size=3, mtime=6),
        }
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file1.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file1.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file2.js", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file2.js", size=1, mtime=1))

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        self.assertEqual(len(result.operations), 2)
        merge_ops = [op for op in result.operations if op.type == types.OperationType.MERGE]
        self.assertEqual(len(merge_ops), 2)

    def test_mixed_text_and_binary_files(self):
        """Test mixed text and binary files use appropriate operations."""
        snap_a = {
            "file.py": make_entry("file.py", size=2, mtime=5),
            "image.png": make_entry("image.png", size=2, mtime=5),
        }
        snap_b = {
            "file.py": make_entry("file.py", size=3, mtime=6),
            "image.png": make_entry("image.png", size=3, mtime=6),
        }
        state = state_store.ProfileState(profile="demo")
        state_store.record_entry(state, self.endpoint_a.id, make_entry("file.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("file.py", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_a.id, make_entry("image.png", size=1, mtime=1))
        state_store.record_entry(state, self.endpoint_b.id, make_entry("image.png", size=1, mtime=1))

        result = planner.plan(self._planner_input(snap_a, snap_b, state))

        self.assertEqual(len(result.operations), 2)
        merge_ops = [op for op in result.operations if op.type == types.OperationType.MERGE]
        copy_ops = [op for op in result.operations if op.type == types.OperationType.COPY]
        self.assertEqual(len(merge_ops), 1)  # file.py
        self.assertEqual(len(copy_ops), 1)   # image.png


if __name__ == "__main__":
    unittest.main()
