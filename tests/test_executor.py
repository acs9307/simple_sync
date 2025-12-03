"""Executor tests ensuring filesystem operations occur."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import types
from simple_sync.engine import executor
from simple_sync.ssh import transport as ssh_transport


def make_endpoint(root: Path) -> types.Endpoint:
    return types.Endpoint(id=str(root), type=types.EndpointType.LOCAL, path=str(root))


class TestExecutor(unittest.TestCase):
    def test_copy_operation_creates_file(self):
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "file.txt").write_text("hello")
            op = types.Operation(
                type=types.OperationType.COPY,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
            )
            executor.apply_operations([op])
            self.assertTrue((dst_root / "file.txt").exists())
            self.assertEqual((dst_root / "file.txt").read_text(), "hello")

    def test_delete_operation_removes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dst_root = Path(tmpdir)
            file_path = dst_root / "delete_me.txt"
            file_path.write_text("bye")
            op = types.Operation(
                type=types.OperationType.DELETE,
                path="delete_me.txt",
                destination=make_endpoint(dst_root),
            )
            executor.apply_operations([op])
            self.assertFalse(file_path.exists())

    def test_dry_run_skips_changes(self):
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "file.txt").write_text("hello")
            copy_op = types.Operation(
                type=types.OperationType.COPY,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
            )
            executor.apply_operations([copy_op], dry_run=True)
            self.assertFalse((dst_root / "file.txt").exists())

    def test_copy_with_suffix(self):
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "file.txt").write_text("hello")
            op = types.Operation(
                type=types.OperationType.COPY,
                path="file.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
                metadata={"target_suffix": "file.txt.conflict-A"},
            )
            executor.apply_operations([op])
            self.assertTrue((dst_root / "file.txt.conflict-A").exists())

    def test_copy_local_to_remote_invokes_ssh_helper(self):
        with tempfile.TemporaryDirectory() as src_tmp:
            src_root = Path(src_tmp)
            (src_root / "file.txt").write_text("hello")
            local_endpoint = types.Endpoint(
                id="local",
                type=types.EndpointType.LOCAL,
                path=str(src_root),
            )
            remote_endpoint = types.Endpoint(
                id="remote",
                type=types.EndpointType.SSH,
                path="/remote",
                host="example.com",
            )
            op = types.Operation(
                type=types.OperationType.COPY,
                path="file.txt",
                source=local_endpoint,
                destination=remote_endpoint,
            )
            with mock.patch("simple_sync.engine.executor.ssh_copy.copy_local_to_remote") as mock_copy:
                executor.apply_operations([op])
        mock_copy.assert_called_once()

    def test_delete_remote_runs_ssh_command(self):
        remote_endpoint = types.Endpoint(
            id="remote",
            type=types.EndpointType.SSH,
            path="/remote",
            host="example.com",
        )
        op = types.Operation(
            type=types.OperationType.DELETE,
            path="obsolete.txt",
            destination=remote_endpoint,
        )
        with mock.patch(
            "simple_sync.engine.executor.ssh_transport.run_ssh_command",
            return_value=ssh_transport.SSHResult(
                exit_code=0, stdout="", stderr="", auth_failed=False, prompt_detected=False
            ),
        ) as mock_run:
            executor.apply_operations([op])
        mock_run.assert_called_once()

    def test_remote_to_remote_copy_relays_via_tempfile(self):
        source_endpoint = types.Endpoint(
            id="source",
            type=types.EndpointType.SSH,
            path="/remote_src",
            host="source.example.com",
        )
        destination_endpoint = types.Endpoint(
            id="dest",
            type=types.EndpointType.SSH,
            path="/remote_dst",
            host="dest.example.com",
        )
        op = types.Operation(
            type=types.OperationType.COPY,
            path="file.txt",
            source=source_endpoint,
            destination=destination_endpoint,
        )
        with mock.patch("simple_sync.engine.executor.ssh_copy.copy_remote_to_local") as mock_pull, mock.patch(
            "simple_sync.engine.executor.ssh_copy.copy_local_to_remote"
        ) as mock_push:
            executor.apply_operations([op])
        mock_pull.assert_called_once()
        mock_push.assert_called_once()

    def test_copy_local_symlink_preserves_link(self):
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            target = src_root / "target.txt"
            target.write_text("contents")
            link = src_root / "link.txt"
            link.symlink_to(target.name)
            op = types.Operation(
                type=types.OperationType.COPY,
                path="link.txt",
                source=make_endpoint(src_root),
                destination=make_endpoint(dst_root),
            )
            executor.apply_operations([op])
            copied = dst_root / "link.txt"
            self.assertTrue(copied.is_symlink())
            self.assertEqual(os.readlink(copied), target.name)

    def test_copy_remote_symlink_to_local_uses_symlink_metadata(self):
        with tempfile.TemporaryDirectory() as dst_tmp:
            dst_root = Path(dst_tmp)
            source_endpoint = types.Endpoint(
                id="source",
                type=types.EndpointType.SSH,
                path="/remote_src",
                host="source.example.com",
            )
            op = types.Operation(
                type=types.OperationType.COPY,
                path="link.txt",
                source=source_endpoint,
                destination=make_endpoint(dst_root),
                metadata={"is_symlink": True, "link_target": "../target.txt"},
            )
            with mock.patch("simple_sync.engine.executor.ssh_copy.copy_remote_to_local") as mock_pull:
                executor.apply_operations([op])
                mock_pull.assert_not_called()
            copied = dst_root / "link.txt"
            self.assertTrue(copied.is_symlink())
            self.assertEqual(os.readlink(copied), "../target.txt")


if __name__ == "__main__":
    unittest.main()
