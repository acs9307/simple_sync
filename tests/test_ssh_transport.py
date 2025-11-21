"""Tests for the SSH transport helper."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from simple_sync.ssh import transport


class TestSSHTransport(unittest.TestCase):
    def test_run_invokes_subprocess_with_expected_args(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with mock.patch("simple_sync.ssh.transport.subprocess.run", return_value=completed) as mock_run:
            result = transport.run_ssh_command(
                host="example.com",
                remote_command=["echo", "hello world"],
                ssh_command=["ssh", "-p", "2222"],
                extra_args=["-i", "~/.ssh/id_ed25519"],
            )
        self.assertEqual(result.exit_code, 0)
        called_args = mock_run.call_args[0][0]
        self.assertEqual(
            called_args,
            ["ssh", "-p", "2222", "-i", "~/.ssh/id_ed25519", "example.com", "echo 'hello world'"],
        )

    def test_auth_failure_detection(self):
        completed = subprocess.CompletedProcess(args=[], returncode=255, stdout="", stderr="Permission denied")
        with mock.patch("simple_sync.ssh.transport.subprocess.run", return_value=completed):
            result = transport.run_ssh_command(host="example.com", remote_command=["true"])
        self.assertTrue(result.auth_failed)

    def test_missing_ssh_command_raises(self):
        with self.assertRaises(transport.SSHCommandError):
            transport.run_ssh_command(host="example.com", remote_command=["true"], ssh_command=[])


if __name__ == "__main__":
    unittest.main()
