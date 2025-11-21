"""Integration-ish tests that simulate SSH operations against localhost."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import types
from simple_sync.engine import executor
from simple_sync.ssh import transport


def _make_endpoints(local_root: Path, remote_root: Path) -> tuple[types.Endpoint, types.Endpoint]:
    local = types.Endpoint(id="local", type=types.EndpointType.LOCAL, path=str(local_root))
    remote = types.Endpoint(id="remote", type=types.EndpointType.SSH, path=str(remote_root), host="localhost")
    return local, remote


class TestSSHCopyIntegration(unittest.TestCase):
    """Exercise executor paths using SSH endpoints without a real server."""

    def test_copy_local_to_remote_applies_bytes(self):
        with tempfile.TemporaryDirectory() as local_tmp, tempfile.TemporaryDirectory() as remote_tmp:
            local_root = Path(local_tmp)
            remote_root = Path(remote_tmp)
            source_file = local_root / "hello.txt"
            source_file.write_text("hello over ssh")
            local_ep, remote_ep = _make_endpoints(local_root, remote_root)

            def fake_copy_local_to_remote(*, host, local_path, remote_path, **_kwargs):
                self.assertEqual(host, "localhost")
                dst = Path(remote_path)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_path, dst)

            op = types.Operation(
                type=types.OperationType.COPY,
                path="hello.txt",
                source=local_ep,
                destination=remote_ep,
            )
            with mock.patch("simple_sync.engine.executor.ssh_copy.copy_local_to_remote", side_effect=fake_copy_local_to_remote):
                executor.apply_operations([op])

            self.assertEqual((remote_root / "hello.txt").read_text(), "hello over ssh")

    def test_copy_remote_to_local_applies_bytes(self):
        with tempfile.TemporaryDirectory() as local_tmp, tempfile.TemporaryDirectory() as remote_tmp:
            local_root = Path(local_tmp)
            remote_root = Path(remote_tmp)
            remote_file = remote_root / "payload.txt"
            remote_file.write_text("from remote")
            local_ep, remote_ep = _make_endpoints(local_root, remote_root)

            def fake_copy_remote_to_local(*, host, remote_path, local_path, **_kwargs):
                self.assertEqual(host, "localhost")
                src = Path(remote_path)
                dst = Path(local_path)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

            op = types.Operation(
                type=types.OperationType.COPY,
                path="payload.txt",
                source=remote_ep,
                destination=local_ep,
            )
            with mock.patch(
                "simple_sync.engine.executor.ssh_copy.copy_remote_to_local", side_effect=fake_copy_remote_to_local
            ):
                executor.apply_operations([op])

            self.assertEqual((local_root / "payload.txt").read_text(), "from remote")

    def test_remote_delete_handles_banner_noise(self):
        with tempfile.TemporaryDirectory() as remote_tmp:
            remote_root = Path(remote_tmp)
            target = remote_root / "obsolete.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("old data")
            _, remote_ep = _make_endpoints(remote_root, remote_root)

            def fake_run_ssh_command(*, remote_command, **_kwargs):
                self.assertIn("obsolete.txt", " ".join(remote_command))
                if target.exists():
                    target.unlink()
                return transport.SSHResult(exit_code=0, stdout="", stderr="Welcome!\nAuthorized users only")

            op = types.Operation(
                type=types.OperationType.DELETE,
                path="obsolete.txt",
                destination=remote_ep,
            )
            with mock.patch("simple_sync.engine.executor.ssh_transport.run_ssh_command", side_effect=fake_run_ssh_command):
                executor.apply_operations([op])

            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
