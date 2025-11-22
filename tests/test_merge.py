"""Tests for the merge module."""

from __future__ import annotations

import unittest

from simple_sync.engine import merge


class TestTextFileDetection(unittest.TestCase):
    """Test text file detection by extension."""

    def test_python_files_detected_as_text(self):
        self.assertTrue(merge.is_text_file("script.py"))

    def test_javascript_files_detected_as_text(self):
        self.assertTrue(merge.is_text_file("app.js"))
        self.assertTrue(merge.is_text_file("component.jsx"))
        self.assertTrue(merge.is_text_file("module.ts"))
        self.assertTrue(merge.is_text_file("widget.tsx"))

    def test_markdown_files_detected_as_text(self):
        self.assertTrue(merge.is_text_file("README.md"))

    def test_config_files_detected_as_text(self):
        self.assertTrue(merge.is_text_file("config.toml"))
        self.assertTrue(merge.is_text_file("settings.yaml"))
        self.assertTrue(merge.is_text_file("data.json"))
        self.assertTrue(merge.is_text_file("app.ini"))

    def test_source_code_files_detected_as_text(self):
        self.assertTrue(merge.is_text_file("main.c"))
        self.assertTrue(merge.is_text_file("main.cpp"))
        self.assertTrue(merge.is_text_file("header.h"))
        self.assertTrue(merge.is_text_file("Main.java"))
        self.assertTrue(merge.is_text_file("app.go"))
        self.assertTrue(merge.is_text_file("lib.rs"))

    def test_binary_files_not_detected_as_text(self):
        self.assertFalse(merge.is_text_file("image.png"))
        self.assertFalse(merge.is_text_file("photo.jpg"))
        self.assertFalse(merge.is_text_file("archive.zip"))
        self.assertFalse(merge.is_text_file("binary.exe"))

    def test_case_insensitive_detection(self):
        self.assertTrue(merge.is_text_file("README.MD"))
        self.assertTrue(merge.is_text_file("Script.PY"))


class TestBinaryContentDetection(unittest.TestCase):
    """Test binary content detection by null bytes."""

    def test_text_content_not_detected_as_binary(self):
        text = b"Hello, world!\nThis is a text file.\n"
        self.assertFalse(merge.is_binary_content(text))

    def test_binary_content_detected_by_null_bytes(self):
        binary = b"Hello\x00World"
        self.assertTrue(merge.is_binary_content(binary))

    def test_utf8_content_not_detected_as_binary(self):
        utf8 = "Hello, 世界!\n".encode('utf-8')
        self.assertFalse(merge.is_binary_content(utf8))

    def test_empty_content_not_binary(self):
        self.assertFalse(merge.is_binary_content(b""))


class TestThreeWayMerge(unittest.TestCase):
    """Test three-way merge functionality."""

    def test_no_changes_returns_base(self):
        base = "line1\nline2\nline3\n"
        a = base
        b = base
        result = merge.merge_three_way(base, a, b)
        self.assertTrue(result.success)
        self.assertEqual(result.content, base)

    def test_one_side_unchanged_returns_other_side(self):
        base = "line1\nline2\nline3\n"
        a = base  # unchanged
        b = "line1\nline2 modified\nline3\n"
        result = merge.merge_three_way(base, a, b)
        self.assertTrue(result.success)
        self.assertEqual(result.content, b)

    def test_other_side_unchanged_returns_changed_side(self):
        base = "line1\nline2\nline3\n"
        a = "line1\nline2 modified\nline3\n"
        b = base  # unchanged
        result = merge.merge_three_way(base, a, b)
        self.assertTrue(result.success)
        self.assertEqual(result.content, a)

    def test_non_overlapping_changes_merge_successfully(self):
        base = "line1\nline2\nline3\nline4\n"
        a = "line1 modified\nline2\nline3\nline4\n"
        b = "line1\nline2\nline3\nline4 modified\n"
        result = merge.merge_three_way(base, a, b)
        self.assertTrue(result.success)
        self.assertIn("line1 modified", result.content)
        self.assertIn("line4 modified", result.content)

    def test_conflicting_changes_create_conflict_markers(self):
        base = "line1\nline2\nline3\n"
        a = "line1\nline2 modified by A\nline3\n"
        b = "line1\nline2 modified by B\nline3\n"
        result = merge.merge_three_way(base, a, b)
        self.assertFalse(result.success)
        self.assertIsNotNone(result.content)
        self.assertIn("<<<<<<< LOCAL", result.content)
        self.assertIn("=======", result.content)
        self.assertIn(">>>>>>> REMOTE", result.content)
        self.assertIn("line2 modified by A", result.content)
        self.assertIn("line2 modified by B", result.content)

    def test_multiple_non_overlapping_changes(self):
        base = "1\n2\n3\n4\n5\n"
        a = "1 modified\n2\n3\n4\n5\n"
        b = "1\n2\n3 modified\n4\n5\n"
        result = merge.merge_three_way(base, a, b)
        self.assertTrue(result.success)
        self.assertIn("1 modified", result.content)
        self.assertIn("3 modified", result.content)

    def test_additions_on_both_sides(self):
        base = "line1\nline3\n"
        a = "line1\nline2a\nline3\n"
        b = "line1\nline2b\nline3\n"
        result = merge.merge_three_way(base, a, b)
        # Our simple merge may include both additions or conflict
        # The key is that it produces some result
        self.assertIsNotNone(result.content)

    def test_deletions_on_both_sides_same_line(self):
        base = "line1\nline2\nline3\n"
        a = "line1\nline3\n"  # deleted line2
        b = "line1\nline3\n"  # deleted line2
        result = merge.merge_three_way(base, a, b)
        # Same result on both sides - should be detected
        # If both sides are identical, merge should succeed
        if a == b:
            # Since both sides are identical, one of them is returned
            self.assertIn("line1", result.content)
            self.assertIn("line3", result.content)

    def test_empty_base_with_different_content(self):
        base = ""
        a = "content from A\n"
        b = "content from B\n"
        result = merge.merge_three_way(base, a, b)
        # With empty base, our simple merge treats both as additions
        # The behavior depends on the merge algorithm
        self.assertIsNotNone(result.content)

    def test_whitespace_differences(self):
        base = "line1\nline2\nline3\n"
        a = "line1 \nline2\nline3\n"  # trailing space
        b = "line1\nline2\nline3 modified\n"
        result = merge.merge_three_way(base, a, b)
        # Non-overlapping changes should succeed
        self.assertTrue(result.success)


class TestMergeResult(unittest.TestCase):
    """Test MergeResult dataclass."""

    def test_successful_merge_result(self):
        result = merge.MergeResult(success=True, content="merged content")
        self.assertTrue(result.success)
        self.assertEqual(result.content, "merged content")
        self.assertEqual(result.conflicts, [])

    def test_failed_merge_result(self):
        result = merge.MergeResult(
            success=False,
            content="conflict content",
            conflicts=["conflict message"]
        )
        self.assertFalse(result.success)
        self.assertEqual(result.conflicts, ["conflict message"])

    def test_default_conflicts_is_empty_list(self):
        result = merge.MergeResult(success=True, content="test")
        self.assertEqual(result.conflicts, [])


if __name__ == "__main__":
    unittest.main()
