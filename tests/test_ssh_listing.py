"""Tests for remote listing utilities."""

from __future__ import annotations

import unittest
from unittest import mock

from simple_sync.ssh import listing


class TestRemoteListing(unittest.TestCase):
    def test_parses_find_output(self):
        body = "\n".join(
            [
                "|d|0|0",
                "dir|d|0|100",
                "dir/file.txt|f|5|200",
            ]
        )
        marker_result = mock.Mock(exit_code=0, body=body, stderr="")
        with mock.patch("simple_sync.ssh.listing.run_with_markers", return_value=marker_result) as mock_run:
            entries = listing.list_remote_entries(host="example.com", root="/data")
        self.assertIn("dir/file.txt", entries)
        file_entry = entries["dir/file.txt"]
        self.assertFalse(file_entry.is_dir)
        mock_run.assert_called_once()

    def test_error_on_non_zero_exit(self):
        marker_result = mock.Mock(exit_code=1, body="", stderr="fail")
        with mock.patch("simple_sync.ssh.listing.run_with_markers", return_value=marker_result):
            with self.assertRaises(listing.RemoteListingError):
                listing.list_remote_entries(host="example.com", root="/data")


if __name__ == "__main__":
    unittest.main()
