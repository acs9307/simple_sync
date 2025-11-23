"""Tests for executor merge operations."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import types
from simple_sync.engine import executor, merge, state_store


def make_endpoint(root: Path) -> types.Endpoint:
    return types.Endpoint(id=str(root), type=types.EndpointType.LOCAL, path=str(root))


class TestExecutorMerge(unittest.TestCase):
    """Test executor handling of MERGE operations."""

    def test_merge_operation_with_non_conflicting_changes(self):
        """Test merge operation attempts to merge or falls back gracefully."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Setup: both sides modified the same file
            # Without base content, simple merge may fall back
            (src_root / "file.txt").write_text("line1\nline2 modified by A\nline3\n")
            (dst_root / "file.txt").write_text("line1\nline2\nline3 modified by B\n")

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            executor.apply_operations([op])

            # Both should have same content after merge or fallback
            src_content = (src_root / "file.txt").read_text()
            dst_content = (dst_root / "file.txt").read_text()

            self.assertEqual(src_content, dst_content)
            # Content should be non-empty
            self.assertTrue(len(src_content) > 0)

    def test_merge_operation_with_conflicting_changes_falls_back(self):
        """Test merge falls back to policy when conflicts occur."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Setup: both sides modified same line (conflict)
            (src_root / "file.txt").write_text("line1\nmodified by A\nline3\n")
            (dst_root / "file.txt").write_text("line1\nmodified by B\nline3\n")

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            # Should fall back to copying from source (newest policy prefers source in our impl)
            executor.apply_operations([op])

            # Verify fallback was applied (both should have same content)
            src_content = (src_root / "file.txt").read_text()
            dst_content = (dst_root / "file.txt").read_text()
            self.assertEqual(src_content, dst_content)

    def test_merge_fallback_newest_prefers_newer_file(self):
        """Test newest fallback copies from the most recently modified file."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            (src_root / "file.txt").write_text("older version\n")
            (dst_root / "file.txt").write_text("newer version\n")

            older_time = time.time() - 120
            newer_time = time.time()
            os.utime(src_root / "file.txt", (older_time, older_time))
            os.utime(dst_root / "file.txt", (newer_time, newer_time))

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            # Force merge failure to exercise fallback path
            with mock.patch("simple_sync.engine.executor._simple_two_way_merge") as mock_merge:
                mock_merge.return_value = merge.MergeResult(success=False, conflicts=["conflict"])
                executor.apply_operations([op])

            self.assertEqual((src_root / "file.txt").read_text(), "newer version\n")
            self.assertEqual((dst_root / "file.txt").read_text(), "newer version\n")

    def test_merge_operation_dry_run(self):
        """Test merge operation in dry-run mode doesn't modify files."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            original_a = "line1\nline2 modified by A\nline3\n"
            original_b = "line1\nline2\nline3 modified by B\n"
            (src_root / "file.txt").write_text(original_a)
            (dst_root / "file.txt").write_text(original_b)

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            executor.apply_operations([op], dry_run=True)

            # Files should remain unchanged
            self.assertEqual((src_root / "file.txt").read_text(), original_a)
            self.assertEqual((dst_root / "file.txt").read_text(), original_b)

    def test_merge_binary_file_falls_back(self):
        """Test that binary files fall back to policy."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Create binary-like content (with null bytes)
            (src_root / "file.dat").write_bytes(b"binary\x00data A")
            (dst_root / "file.dat").write_bytes(b"binary\x00data B")

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.dat",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            # Should fall back to copying
            executor.apply_operations([op])

            # Both should have same content (fallback applied)
            src_content = (src_root / "file.dat").read_bytes()
            dst_content = (dst_root / "file.dat").read_bytes()
            self.assertEqual(src_content, dst_content)

    def test_merge_creates_parent_directories(self):
        """Test merge operation creates parent directories as needed."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Create nested file
            (src_root / "subdir").mkdir()
            (src_root / "subdir" / "file.txt").write_text("content A\n")
            (dst_root / "subdir").mkdir()
            (dst_root / "subdir" / "file.txt").write_text("content B\n")

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="subdir/file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            executor.apply_operations([op])

            # Verify both files exist
            self.assertTrue((src_root / "subdir" / "file.txt").exists())
            self.assertTrue((dst_root / "subdir" / "file.txt").exists())

    def test_merge_with_manual_fallback_raises_error(self):
        """Test merge with manual fallback policy raises on conflict."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Setup conflicting changes
            (src_root / "file.txt").write_text("line1\nmodified by A\nline3\n")
            (dst_root / "file.txt").write_text("line1\nmodified by B\nline3\n")

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={
                    "fallback_policy": "manual",
                    "fallback_manual_behavior": "copy_both",
                },
            )

            # Should raise ExecutionError for manual resolution
            with self.assertRaises(executor.ExecutionError) as ctx:
                executor.apply_operations([op])

            self.assertIn("Manual resolution required", str(ctx.exception))

    def test_merge_missing_file_falls_back(self):
        """Test merge with missing file falls back gracefully."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Only create file on one side
            (src_root / "file.txt").write_text("content A\n")
            # dst side missing

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            # Should fall back and copy
            executor.apply_operations([op])

            # Destination should now have the file
            self.assertTrue((dst_root / "file.txt").exists())

    def test_merge_preserves_content(self):
        """Test that merge operation produces consistent output."""
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)

            # Setup files with some content
            src_content = "# Header\nline1\nline2 modified\nline3\n"
            dst_content = "# Header\nline1\nline2\nline3 modified\n"
            (src_root / "file.py").write_text(src_content)
            (dst_root / "file.py").write_text(dst_content)

            op = types.Operation(
                type=types.OperationType.MERGE,
                path="file.py",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"fallback_policy": "newest"},
            )

            executor.apply_operations([op])

            # Verify both sides have the same content
            merged_a = (src_root / "file.py").read_text()
            merged_b = (dst_root / "file.py").read_text()
            self.assertEqual(merged_a, merged_b)
            # Should contain the header
            self.assertIn("# Header", merged_a)

    def test_merge_operation_without_source_raises_error(self):
        """Test merge operation without source endpoint raises error."""
        op = types.Operation(
            type=types.OperationType.MERGE,
            path="file.txt",
            destination=make_endpoint(Path("/tmp")),
            metadata={"fallback_policy": "newest"},
        )

        with self.assertRaises(executor.ExecutionError) as ctx:
            executor.apply_operations([op])

        self.assertIn("source and destination", str(ctx.exception))

    def test_merge_operation_without_destination_raises_error(self):
        """Test merge operation without destination endpoint raises error."""
        op = types.Operation(
            type=types.OperationType.MERGE,
            path="file.txt",
            source=make_endpoint(Path("/tmp")),
            metadata={"fallback_policy": "newest"},
        )

        with self.assertRaises(executor.ExecutionError) as ctx:
            executor.apply_operations([op])

        self.assertIn("source and destination", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
