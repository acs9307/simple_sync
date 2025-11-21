"""Tests for remote copy helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from simple_sync.ssh import copy


class TestRemoteCopy(unittest.TestCase):
    def test_copy_local_to_remote_builds_command(self):
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")) as mock_run:
            copy.copy_local_to_remote(
                host="example.com",
                local_path="/tmp/file.txt",
                remote_path="/remote/file.txt",
                scp_command=["scp", "-P", "2222"],
                extra_args=["-i", "~/.ssh/id"],
            )
        args = mock_run.call_args[0][0]
        self.assertEqual(
            args,
            ["scp", "-P", "2222", "-i", "~/.ssh/id", "/tmp/file.txt", "example.com:/remote/file.txt"],
        )

    def test_copy_remote_to_local_error(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail")
        with mock.patch("subprocess.run", return_value=completed):
            with self.assertRaises(copy.RemoteCopyError):
                copy.copy_remote_to_local(
                    host="example.com",
                    remote_path="/remote/file",
                    local_path="local",
                )

    def test_copy_remote_prompt_detected(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Password:")
        with mock.patch("subprocess.run", return_value=completed):
            with self.assertRaises(copy.RemoteCopyError) as err:
                copy.copy_remote_to_local(
                    host="example.com",
                    remote_path="/remote/file",
                    local_path="local",
                )
        self.assertIn("prompt", str(err.exception))


if __name__ == "__main__":
    unittest.main()
