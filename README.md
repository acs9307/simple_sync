# simple_sync

`simple_sync` aims to be a friendly, transparent tool for synchronizing directories across machines. The long-term vision is:

- Provide a declarative configuration format describing sync profiles, schedules, and conflict policies.
- Offer a CLI that can run one-off synchronizations as well as a long-running daemon.
- Support multiple endpoints (local paths first, eventually SSH and cloud remotes).
- Keep users informed with clear logging, dry-run support, and good defaults.

This repository is under active construction. Track the `TODO.txt` file for the current roadmap.

## Daemon usage

`simple_sync` ships with a lightweight daemon runner for scheduled profiles. To run it in the foreground for debugging:

```bash
simple-sync daemon start --config-dir /path/to/config --once
```

For long-running setups, consider a systemd service file such as:

```
[Unit]
Description=Simple Sync Daemon
After=network-online.target

[Service]
ExecStart=/usr/bin/simple-sync daemon start --config-dir /home/user/.config/simple_sync
Restart=on-failure

[Install]
WantedBy=default.target
```

On macOS launchd you can create a plist pointing to the same command. These examples assume you've configured schedules (`schedule.enabled`) within your profiles.

## Installation

The easiest way to install is via [pipx](https://pipx.pypa.io):

```bash
pipx install simple-sync
```

This keeps the CLI isolated while making the `simple-sync` command available on your PATH. Alternatively, you can use `pip install simple-sync` inside a virtual environment.

## Standalone binaries

For macOS and Linux targets you can build a standalone bundle with [PyInstaller](https://pyinstaller.org):

```bash
pip install '.[binary]'
./scripts/build-binary.sh
```

The resulting `dist/simple-sync/simple-sync` executable includes its own Python runtime; no system Python is required to run it. Integration tests in `tests/test_binary_build.py` exercise both `run` and `daemon` paths against the built binary.

## Windows support (preview)

Windows 10/11 is supported for local↔local profiles and the CLI/daemon. Configuration lives under `%APPDATA%\simple_sync` by default, mirroring the Linux/macOS layout. Remote endpoints rely on `ssh`/`scp` being on your `PATH`; install the built-in OpenSSH (Windows Optional Features) or Git for Windows to provide these binaries. Path handling is normalized to POSIX-style separators internally, so ignore patterns should use `/`. Known caveats: remote discovery uses POSIX `find` on the SSH host, and symlink or alternate stream semantics on NTFS are not yet considered.

## Dockerized SSH/agent harness

For a repeatable agent/pre-connect test bed, build and run the included container:

```bash
docker build -t simple-sync-ssh-agent -f docker/ssh-agent/Dockerfile .
docker run --rm -it -p 2222:2222 simple-sync-ssh-agent
```

The container starts `sshd` on port 2222, launches an `ssh-agent` at `/tmp/ssh-agent.sock`, and seeds a demo profile at `/root/.config/simple_sync/profiles/demo.toml` that uses `pre_connect_command = "ssh-add -l"` and points a remote endpoint at `localhost:2222`. Inside the container you can run:

```bash
simple-sync --config-dir /root/.config/simple_sync run demo --dry-run
```

to verify the agent/pre-connect flow without needing a hardware token.
