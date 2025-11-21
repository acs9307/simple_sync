"""Tests for the local snapshot builder."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from simple_sync.engine import snapshot


class TestSnapshotBuilder(unittest.TestCase):
    def test_build_snapshot_collects_files_and_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "dir").mkdir()
            file_path = base / "dir" / "file.txt"
            file_path.write_text("hello")
            snapshot_result = snapshot.build_snapshot(base)
            self.assertIn("dir", snapshot_result.entries)
            self.assertIn("dir/file.txt", snapshot_result.entries)
            file_entry = snapshot_result.entries["dir/file.txt"]
            self.assertFalse(file_entry.is_dir)
            self.assertEqual(file_entry.size, 5)

    def test_ignore_patterns_skip_files_and_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "ignored").mkdir()
            (base / "ignored" / "file.txt").write_text("ignored")
            (base / "keep.tmp").write_text("tmp")
            result = snapshot.build_snapshot(base, ignore_patterns=["ignored*", "*.tmp"])
            self.assertNotIn("ignored", result.entries)
            self.assertNotIn("ignored/file.txt", result.entries)
            self.assertNotIn("keep.tmp", result.entries)

    def test_missing_root_errors(self):
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.build_snapshot("/path/that/does/not/exist")


if __name__ == "__main__":
    unittest.main()
