"""Tests for SSH marker commands."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from simple_sync.ssh import commands


class TestSSHMarkerCommands(unittest.TestCase):
    def test_wrap_remote_command_includes_markers(self):
        wrapped = commands.wrap_remote_command(["echo", "hello"])
        self.assertIn(commands.BEGIN_MARKER, " ".join(wrapped))
        self.assertIn(commands.END_MARKER, " ".join(wrapped))

    def test_run_with_markers_extracts_between_markers(self):
        stdout = f"banner\n{commands.BEGIN_MARKER}\ndata\nmore\n{commands.END_MARKER}\nnoise"
        with mock.patch("simple_sync.ssh.commands.run_ssh_command", return_value=commands.SSHResult(0, stdout, "")):
            result = commands.run_with_markers(host="example.com", remote_command=["ls"])
        self.assertEqual(result.body, "data\nmore")


if __name__ == "__main__":
    unittest.main()
