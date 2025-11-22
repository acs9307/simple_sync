"""Tests for the state store module."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from simple_sync.engine import state_store
from simple_sync import types


class TestStateStore(unittest.TestCase):
    def test_load_missing_profile_returns_empty_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = state_store.load_state("demo", Path(tmpdir))
        self.assertEqual(state.profile, "demo")
        self.assertEqual(state.endpoints, {})

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = state_store.ProfileState(profile="demo")
            entry = types.FileEntry(path="file.txt", is_dir=False, size=10, mtime=1.0)
            state_store.record_entry(state, "A", entry)
            path = state_store.save_state(state, Path(tmpdir))
            loaded = state_store.load_state("demo", Path(tmpdir))
        self.assertEqual(path.name, "demo.json")
        stored = state_store.get_last_entry(loaded, "A", "file.txt")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.size, 10)

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "demo.json").write_text("{invalid}")
            with self.assertRaises(state_store.StateStoreError):
                state_store.load_state("demo", Path(tmpdir))

    def test_conflict_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = state_store.ProfileState(profile="demo")
            state_store.record_conflict(
                state,
                path="file.txt",
                reason="manual_copy_both",
                endpoints=("A", "B"),
                resolution="copy_both",
                timestamp=1234.0,
                metadata={"note": "manual resolution"},
            )
            state_store.save_state(state, Path(tmpdir))
            loaded = state_store.load_state("demo", Path(tmpdir))
        self.assertEqual(len(loaded.conflicts), 1)
        conflict = loaded.conflicts[0]
        self.assertEqual(conflict.path, "file.txt")
        self.assertEqual(conflict.reason, "manual_copy_both")
        self.assertEqual(conflict.resolution, "copy_both")
        self.assertEqual(conflict.timestamp, 1234.0)
        self.assertEqual(conflict.metadata.get("note"), "manual resolution")


if __name__ == "__main__":
    unittest.main()
