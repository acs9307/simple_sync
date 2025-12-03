"""Tests for the local snapshot builder."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import types
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

    def test_dangling_symlink_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "missing.txt"
            link = base / "link.txt"
            link.symlink_to(target)
            result = snapshot.build_snapshot(base)
        self.assertIn("link.txt", result.entries)
        entry = result.entries["link.txt"]
        self.assertTrue(entry.is_symlink)
        self.assertFalse(entry.is_dir)
        self.assertEqual(entry.size, 0)

    def test_missing_root_errors(self):
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.build_snapshot("/path/that/does/not/exist")


class TestRemoteSnapshot(unittest.TestCase):
    def test_remote_snapshot_uses_listing_and_respects_ignore(self):
        endpoint = types.Endpoint(
            id="remote",
            type=types.EndpointType.SSH,
            path="/srv/data",
            host="example.com",
            ssh_command="ssh",
        )
        mock_entries = {
            ".": types.FileEntry(path=".", is_dir=True, size=0, mtime=0),
            "keep.txt": types.FileEntry(path="keep.txt", is_dir=False, size=5, mtime=10),
            "ignored.tmp": types.FileEntry(path="ignored.tmp", is_dir=False, size=1, mtime=10),
        }
        with mock.patch("simple_sync.engine.snapshot.listing.list_remote_entries", return_value=mock_entries) as mock_list:
            result = snapshot.build_snapshot_for_endpoint(
                endpoint, ignore_patterns=["*.tmp"], ssh_command="ssh"
            )
        self.assertIn("keep.txt", result.entries)
        self.assertNotIn("ignored.tmp", result.entries)
        self.assertNotIn(".", result.entries)
        mock_list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
