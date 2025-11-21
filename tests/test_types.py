"""Tests for the core synchronization data types."""

from __future__ import annotations

import unittest

from simple_sync import types


class TestEndpoint(unittest.TestCase):
    def test_local_endpoint_path_normalized(self):
        endpoint = types.Endpoint(id="local", type=types.EndpointType.LOCAL, path="data/project")
        self.assertTrue(str(endpoint.path).endswith("data/project"))

    def test_ssh_endpoint_requires_host(self):
        with self.assertRaises(ValueError):
            types.Endpoint(id="remote", type=types.EndpointType.SSH, path="remote/path")


class TestNormalizeRelativePath(unittest.TestCase):
    def test_disallows_absolute_paths(self):
        with self.assertRaises(ValueError):
            types.normalize_relative_path("/tmp/file")

    def test_disallows_parent_escape(self):
        with self.assertRaises(ValueError):
            types.normalize_relative_path("../secret.txt")

    def test_normalizes_current_dir(self):
        self.assertEqual(types.normalize_relative_path("./folder/file.txt"), "folder/file.txt")
        self.assertEqual(types.normalize_relative_path("."), ".")

    def test_windows_style_separators_are_normalized(self):
        self.assertEqual(types.normalize_relative_path(r"dir\\nested\\file.txt"), "dir/nested/file.txt")
        with self.assertRaises(ValueError):
            types.normalize_relative_path(r"C:\\data\\file.txt")


class TestMetadataContainers(unittest.TestCase):
    def test_file_entry_normalizes_path(self):
        entry = types.FileEntry(path="./dir/file.txt", is_dir=False, size=10, mtime=1.0)
        self.assertEqual(entry.path, "dir/file.txt")

    def test_operation_normalizes_path(self):
        op = types.Operation(type=types.OperationType.COPY, path="./foo/bar")
        self.assertEqual(op.path, "foo/bar")

    def test_conflict_stores_endpoints(self):
        endpoint = types.Endpoint(id="one", type=types.EndpointType.LOCAL, path=".")
        conflict = types.Conflict(path="data.txt", endpoints=(endpoint, endpoint), reason="divergent")
        self.assertEqual(conflict.path, "data.txt")


if __name__ == "__main__":
    unittest.main()
