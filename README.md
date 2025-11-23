# simple_sync

`simple_sync` aims to be a friendly, transparent tool for synchronizing directories across machines. The long-term vision is:

- Provide a declarative configuration format describing sync profiles, schedules, and conflict policies.
- Offer a CLI that can run one-off synchronizations as well as a long-running daemon.
- Support multiple endpoints (local paths first, eventually SSH and cloud remotes).
- Keep users informed with clear logging, dry-run support, and good defaults.

This repository is under active construction. Track the `TODO.txt` file for the current roadmap.

## Getting Started

The fastest way to sync two directories is using the interactive `init` command:

```bash
simple-sync init my-sync
```

This will prompt you for:
- Profile name (defaults to "my-sync")
- Description
- First endpoint (local path)
- Second endpoint (can be local or SSH)
- Whether to include default ignore patterns (.git, node_modules, __pycache__)

Then run the sync:

```bash
simple-sync run my-sync
```

### Manual Profile Creation

Alternatively, create a profile file manually at `~/.config/simple_sync/profiles/my-sync.toml`:

```toml
[profile]
name = "my-sync"
description = "One-off sync between two directories"

[conflict]
policy = "newest"  # Use newest file when conflicts occur

[ignore]
patterns = [".git", "node_modules", "__pycache__"]

[endpoints.source]
type = "local"
path = "/path/to/source"

[endpoints.destination]
type = "local"
path = "/path/to/destination"
```

Then run:

```bash
simple-sync run my-sync
```

### Useful Options

- `--dry-run` - See what would happen without making changes:
  ```bash
  simple-sync run my-sync --dry-run
  ```

- `--verbose` - Get more detailed output:
  ```bash
  simple-sync -v run my-sync
  ```

The profile will be saved for future use, but you can run it once and ignore it afterward. The tool handles bidirectional sync automatically using the "newest" policy by default.

### Tab Completion

`simple-sync` supports intelligent tab completion for bash, zsh, fish, and tcsh shells. Completion works for:
- Commands (run, profiles, status, etc.)
- Profile names from your configuration
- Command-line options

**Quick setup:**

```bash
simple-sync completion --install
```

This auto-detects your shell and installs completion. After installation, restart your shell or source your rc file:

```bash
# Bash
source ~/.bashrc

# Zsh
source ~/.zshrc

# Fish - just restart the shell
```

**Manual setup:**

If you prefer manual installation, see instructions with:

```bash
simple-sync completion
```

Once installed, you can use tab completion:

```bash
simple-sync run <TAB>        # Shows available profiles
simple-sync status <TAB>     # Shows available profiles
simple-sync <TAB>            # Shows available commands
```

### Text File Merging

When both directories have modified the same file between syncs, `simple-sync` can attempt to automatically merge text files (similar to git merge). This feature is enabled by default and works for common text file formats (.py, .js, .md, etc.).

The merge settings are configured in the `[conflict]` section:

```toml
[conflict]
policy = "newest"
merge_text_files = true       # Enable automatic merging for text files (default: true)
merge_fallback = "newest"     # Fallback policy if merge fails (newest, manual, or prefer)
```

**How it works:**

1. When both endpoints have modified a text file, `simple-sync` attempts to merge the changes automatically
2. If the merge succeeds (no overlapping changes), the merged content is written to both endpoints
3. If the merge fails (conflicting changes), it falls back to the configured `merge_fallback` policy
4. Binary files and non-text formats always use the configured conflict policy (no merge attempt)

**Supported fallback policies:**

- `newest` - Use the most recently modified version
- `manual` - Require manual resolution (creates conflict files)
- `prefer` - Use the preferred endpoint (requires `prefer` field to be set)

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
