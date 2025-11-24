"""Command-line interface for simple_sync."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

try:
    import argcomplete
    ARGCOMPLETE_AVAILABLE = True
except ImportError:
    ARGCOMPLETE_AVAILABLE = False

from . import __version__, config, types
from .daemon import DaemonRunner
from .engine import executor, planner, snapshot, state_store
from .logging import configure_logging

# Import completers if argcomplete is available
if ARGCOMPLETE_AVAILABLE:
    from . import completion

Handler = Callable[[argparse.Namespace], int]
logger = logging.getLogger(__name__)
DEFAULT_IGNORE_PATTERNS = [".git", "node_modules", "__pycache__"]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser with all supported subcommands."""
    parser = argparse.ArgumentParser(
        prog="simple-sync",
        description="Profile-driven file synchronization utility.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config-dir",
        help="Override the configuration directory (defaults to ~/.config/simple_sync).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (can be repeated).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Decrease logging verbosity (can be repeated).",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Execute a synchronization run for a profile.",
    )
    profile_arg = run_parser.add_argument("profile", help="Name of the profile to synchronize.")
    if ARGCOMPLETE_AVAILABLE:
        profile_arg.completer = completion.profile_completer
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan actions without touching the filesystem.",
    )
    run_parser.set_defaults(func=_handle_run)

    profiles_parser = subparsers.add_parser(
        "profiles",
        help="List configured profiles.",
    )
    profiles_parser.add_argument(
        "--details",
        action="store_true",
        help="Show extended profile information (includes file paths).",
    )
    profiles_parser.set_defaults(func=_handle_profiles)

    init_parser = subparsers.add_parser(
        "init",
        help="Create a new profile via interactive prompts.",
    )
    init_parser.add_argument(
        "profile",
        nargs="?",
        help="Optional name for the new profile.",
    )
    init_parser.set_defaults(func=_handle_init)

    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Manage the long-running synchronization daemon.",
    )
    daemon_parser.add_argument(
        "action",
        choices=("start",),
        help="Daemon action to perform.",
    )
    daemon_parser.add_argument(
        "--once",
        action="store_true",
        help="Run scheduled profiles once then exit.",
    )
    daemon_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Keep output in the foreground instead of logging to per-profile files.",
    )
    daemon_parser.set_defaults(func=_handle_daemon)

    status_parser = subparsers.add_parser(
        "status",
        help="Show the latest sync status for a profile.",
    )
    status_profile_arg = status_parser.add_argument(
        "profile",
        nargs="?",
        help="Profile to inspect; defaults to all.",
    )
    if ARGCOMPLETE_AVAILABLE:
        status_profile_arg.completer = completion.profile_completer
    status_parser.set_defaults(func=_handle_status)

    conflicts_parser = subparsers.add_parser(
        "conflicts",
        help="Inspect outstanding conflicts for a profile.",
    )
    conflicts_profile_arg = conflicts_parser.add_argument(
        "profile",
        help="Profile to inspect for conflicts.",
    )
    if ARGCOMPLETE_AVAILABLE:
        conflicts_profile_arg.completer = completion.profile_completer
    conflicts_parser.set_defaults(func=_handle_conflicts)

    completion_parser = subparsers.add_parser(
        "completion",
        help="Install or show tab completion setup instructions.",
    )
    completion_parser.add_argument(
        "--install",
        action="store_true",
        help="Install completion for the current shell (bash/zsh/fish).",
    )
    completion_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish", "tcsh"],
        help="Target shell for completion (auto-detected if not specified).",
    )
    completion_parser.set_defaults(func=_handle_completion)

    return parser


def _handle_run(args: argparse.Namespace) -> int:
    runner = SyncRunner(config_dir=args.config_dir)
    try:
        runner.run(profile_name=args.profile, dry_run=args.dry_run)
    except (
        config.ConfigError,
        snapshot.SnapshotError,
        state_store.StateStoreError,
        executor.ExecutionError,
        RuntimeError,
    ) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _handle_profiles(args: argparse.Namespace) -> int:
    try:
        summaries = _gather_profile_summaries(args.config_dir)
    except config.ConfigError as exc:
        logger.error("%s", exc)
        return 1
    if not summaries:
        print("No profiles found.")
        return 0
    _print_profile_table(summaries, show_details=args.details)
    return 0


def _handle_init(args: argparse.Namespace) -> int:
    wizard = InitWizard(config_dir=args.config_dir)
    try:
        profile_path = wizard.run(args.profile)
    except config.ConfigError as exc:
        logger.error("%s", exc)
        return 1
    logger.info("Profile created at %s.", profile_path)
    return 0


def _handle_daemon(args: argparse.Namespace) -> int:
    if args.action == "start":
        runner = DaemonRunner(config_dir=args.config_dir)
        runner.run_forever(run_once=getattr(args, "once", False), foreground=getattr(args, "foreground", False))
        return 0
    logger.error("Unsupported daemon action '%s'.", args.action)
    return 1


def _handle_status(args: argparse.Namespace) -> int:
    try:
        summaries = _gather_profile_summaries(args.config_dir, include_conflicts=True)
    except config.ConfigError as exc:
        logger.error("%s", exc)
        return 1
    if args.profile:
        summaries = [summary for summary in summaries if summary.name == args.profile]
        if not summaries:
            logger.error("Profile '%s' not found.", args.profile)
            return 1
    if not summaries:
        print("No profiles found.")
        return 0
    _print_status_table(summaries)
    return 0


def _handle_conflicts(args: argparse.Namespace) -> int:
    if not args.profile:
        logger.error("Profile name is required.")
        return 1
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else None
    base = config.ensure_config_structure(config_dir)
    try:
        state = state_store.load_state(args.profile, base)
    except state_store.StateStoreError as exc:
        logger.error("%s", exc)
        return 1
    if not state.conflicts:
        print(f"No conflicts recorded for profile '{args.profile}'.")
        return 0
    for record in state.conflicts:
        endpoints = " vs ".join(record.endpoints)
        stamp = _format_timestamp(record.timestamp) if getattr(record, "timestamp", None) else "unknown"
        resolution = getattr(record, "resolution", None) or (record.metadata.get("resolution") if record.metadata else None)
        print(f"{record.path}: {record.reason} ({endpoints}) at {stamp}")
        if resolution:
            print(f"  resolution: {resolution}")
        if record.metadata:
            print(f"  metadata: {record.metadata}")
    return 0


def _handle_completion(args: argparse.Namespace) -> int:
    """Handle the completion command for installing shell completion."""
    if not ARGCOMPLETE_AVAILABLE:
        print("Tab completion requires the 'argcomplete' package.")
        print("Install it with: pip install argcomplete")
        return 1

    import shutil

    # Detect shell if not specified
    shell = args.shell
    if not shell:
        shell_env = Path(os.environ.get("SHELL", "")).name
        if shell_env in {"bash", "zsh", "fish", "tcsh"}:
            shell = shell_env
        elif os.environ.get("BASH_VERSION"):
            shell = "bash"
        elif os.environ.get("ZSH_VERSION"):
            shell = "zsh"
        if not shell:
            print("Could not auto-detect shell. Please specify with --shell")
            return 1

    if args.install:
        # Attempt to install completion
        try:
            if shell == "bash":
                completion_script = "eval \"$(register-python-argcomplete simple-sync)\""
                bashrc = Path.home() / ".bashrc"

                # Check if already installed
                if bashrc.exists() and completion_script in bashrc.read_text():
                    print("Completion already installed in ~/.bashrc")
                else:
                    with bashrc.open("a") as f:
                        f.write(f"\n# simple-sync completion\n{completion_script}\n")
                    print("Completion installed in ~/.bashrc")
                    print("Run 'source ~/.bashrc' or restart your shell to activate.")

            elif shell == "zsh":
                completion_script = "\n".join(
                    [
                        "autoload -U bashcompinit",
                        "bashcompinit",
                        "eval \"$(register-python-argcomplete --shell zsh simple-sync)\"",
                    ]
                )
                zshrc = Path.home() / ".zshrc"

                if zshrc.exists() and completion_script in zshrc.read_text():
                    print("Completion already installed in ~/.zshrc")
                else:
                    with zshrc.open("a") as f:
                        f.write(f"\n# simple-sync completion\n{completion_script}\n")
                    print("Completion installed in ~/.zshrc")
                    print("Run 'source ~/.zshrc' or restart your shell to activate.")

            elif shell == "fish":
                fish_dir = Path.home() / ".config" / "fish" / "completions"
                fish_dir.mkdir(parents=True, exist_ok=True)
                fish_file = fish_dir / "simple-sync.fish"

                result = subprocess.run(
                    ["register-python-argcomplete", "--shell", "fish", "simple-sync"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    fish_file.write_text(result.stdout)
                    print(f"Completion installed in {fish_file}")
                    print("Restart your shell to activate.")
                else:
                    print("Failed to generate fish completion script")
                    return 1

            elif shell == "tcsh":
                print("tcsh completion requires manual setup.")
                print("Add the following to your ~/.tcshrc:")
                print("  eval `register-python-argcomplete --shell tcsh simple-sync`")

        except Exception as exc:
            logger.error("Failed to install completion: %s", exc)
            return 1

        return 0

    else:
        # Show instructions
        print(f"To enable tab completion for {shell}:")
        print()

        if shell == "bash":
            print("1. Ensure argcomplete is installed:")
            print("   pip install argcomplete")
            print()
            print("2. Add to ~/.bashrc:")
            print("   eval \"$(register-python-argcomplete simple-sync)\"")
            print()
            print("3. Reload your shell:")
            print("   source ~/.bashrc")

        elif shell == "zsh":
            print("1. Ensure argcomplete is installed:")
            print("   pip install argcomplete")
            print()
            print("2. Add to ~/.zshrc:")
            print("   autoload -U bashcompinit")
            print("   bashcompinit")
            print("   eval \"$(register-python-argcomplete --shell zsh simple-sync)\"")
            print()
            print("3. Reload your shell:")
            print("   source ~/.zshrc")

        elif shell == "fish":
            print("1. Ensure argcomplete is installed:")
            print("   pip install argcomplete")
            print()
            print("2. Generate and save completion script:")
            print("   register-python-argcomplete --shell fish simple-sync > ~/.config/fish/completions/simple-sync.fish")

        elif shell == "tcsh":
            print("1. Ensure argcomplete is installed:")
            print("   pip install argcomplete")
            print()
            print("2. Add to ~/.tcshrc:")
            print("   eval `register-python-argcomplete --shell tcsh simple-sync`")

        print()
        print("Or run: simple-sync completion --install")

        return 0


class SyncRunner:
    """Coordinates snapshots, planner, executor, and state persistence."""

    def __init__(self, *, config_dir: Optional[str] = None):
        self._config_dir = Path(config_dir).expanduser() if config_dir else None
        self._preconnect_done: bool = False

    def run(self, *, profile_name: str, dry_run: bool) -> None:
        base = config.ensure_config_structure(self._config_dir)
        profile_cfg = config.load_profile(profile_name, base)
        endpoint_a, endpoint_b = self._prepare_endpoints(profile_cfg)
        ignore_patterns = profile_cfg.ignore.patterns

        ssh_env = profile_cfg.ssh.env if profile_cfg.ssh else {}
        preconnect_command = profile_cfg.ssh.pre_connect_command if profile_cfg.ssh else None
        if not preconnect_command:
            for endpoint in (endpoint_a, endpoint_b):
                if endpoint.pre_connect_command:
                    preconnect_command = endpoint.pre_connect_command
                    break
        if preconnect_command and not self._preconnect_done:
            self._run_preconnect(preconnect_command, ssh_env)
            self._preconnect_done = True

        snap_a = snapshot.build_snapshot_for_endpoint(
            endpoint_a, ignore_patterns=ignore_patterns, ssh_command=endpoint_a.ssh_command
        )
        snap_b = snapshot.build_snapshot_for_endpoint(
            endpoint_b, ignore_patterns=ignore_patterns, ssh_command=endpoint_b.ssh_command
        )
        state = state_store.load_state(profile_cfg.profile.name, base)
        plan_input = planner.PlannerInput(
            profile=profile_cfg.profile.name,
            snapshot_a=snap_a.entries,
            snapshot_b=snap_b.entries,
            endpoint_a=endpoint_a,
            endpoint_b=endpoint_b,
            state=state,
            policy=profile_cfg.conflict.policy,
            prefer_endpoint=profile_cfg.conflict.prefer,
            manual_behavior=profile_cfg.conflict.manual_behavior,
            merge_text_files=profile_cfg.conflict.merge_text_files,
            merge_fallback=profile_cfg.conflict.merge_fallback,
        )
        plan_result = planner.plan(plan_input)
        self._log_plan(plan_result)

        blocking_conflicts = [c for c in plan_result.conflicts if c.reason != "manual_copy_both"]
        if blocking_conflicts:
            if not dry_run:
                self._persist_state(
                    profile_cfg.profile.name,
                    endpoint_a,
                    endpoint_b,
                    ignore_patterns,
                    base,
                    plan_result.conflicts,
                )
            raise RuntimeError("Conflicts detected; resolve before rerunning.")
        if plan_result.conflicts:
            logger.warning("Conflicts recorded with manual policy; review generated *.conflict-* files.")

        if dry_run:
            logger.info("Dry-run complete; no filesystem changes applied.")
            return

        if plan_result.operations:
            try:
                executor.apply_operations(plan_result.operations, dry_run=False, state=state)
            except executor.ExecutionError as exc:
                if "Permission denied" in str(exc):
                    raise RuntimeError("SSH authentication failed. Check your agent or credentials.") from exc
                raise
        else:
            logger.info("No operations required; verifying state.")

        saved_path = self._persist_state(
            profile_cfg.profile.name,
            endpoint_a,
            endpoint_b,
            ignore_patterns,
            base,
            plan_result.conflicts,
        )
        logger.info("Synchronization complete. State saved to %s.", saved_path)

    def _prepare_endpoints(self, profile_cfg: config.ProfileConfig) -> tuple[types.Endpoint, types.Endpoint]:
        endpoint_blocks = list(profile_cfg.endpoints.values())
        if len(endpoint_blocks) != 2:
            raise config.ConfigError("Profile must define exactly two endpoints for this run mode.")

        endpoints: List[types.Endpoint] = []
        default_ssh_command = profile_cfg.ssh.ssh_command if profile_cfg.ssh else None
        default_preconnect = profile_cfg.ssh.pre_connect_command if profile_cfg.ssh else None
        for block in endpoint_blocks:
            if block.type == "local":
                if not block.path:
                    raise config.ConfigError(f"Endpoint '{block.name}' is missing a path.")
                root = Path(block.path).expanduser()
                if root.exists() and not root.is_dir():
                    raise config.ConfigError(f"Endpoint '{block.name}' path {root} is not a directory.")
                root.mkdir(parents=True, exist_ok=True)
                endpoints.append(
                    types.Endpoint(
                        id=block.name,
                        type=types.EndpointType.LOCAL,
                        path=root,
                        description=block.description,
                    )
                )
            elif block.type == "ssh":
                if not block.host:
                    raise config.ConfigError(f"Endpoint '{block.name}' (ssh) is missing 'host'.")
                if not block.path:
                    raise config.ConfigError(f"Endpoint '{block.name}' (ssh) is missing 'path'.")
                endpoints.append(
                    types.Endpoint(
                        id=block.name,
                        type=types.EndpointType.SSH,
                        path=Path(block.path),
                        host=block.host,
                        description=block.description,
                        ssh_command=block.ssh_command or default_ssh_command,
                        pre_connect_command=block.pre_connect_command or default_preconnect,
                    )
                )
            else:
                raise config.ConfigError(f"Unsupported endpoint type '{block.type}'.")
        return endpoints[0], endpoints[1]

    def _persist_state(
        self,
        profile_name: str,
        endpoint_a: types.Endpoint,
        endpoint_b: types.Endpoint,
        ignore_patterns: List[str],
        base_dir: Path,
        conflicts: List[types.Conflict],
    ) -> Path:
        snap_a = snapshot.build_snapshot_for_endpoint(
            endpoint_a, ignore_patterns=ignore_patterns, ssh_command=endpoint_a.ssh_command
        )
        snap_b = snapshot.build_snapshot_for_endpoint(
            endpoint_b, ignore_patterns=ignore_patterns, ssh_command=endpoint_b.ssh_command
        )
        next_state = state_store.ProfileState(profile=profile_name)
        for entry in snap_a.entries.values():
            state_store.record_entry(next_state, endpoint_a.id, entry)
        for entry in snap_b.entries.values():
            state_store.record_entry(next_state, endpoint_b.id, entry)
        for conflict in conflicts:
            state_store.record_conflict(
                next_state,
                path=conflict.path,
                reason=conflict.reason,
                endpoints=(conflict.endpoints[0].id, conflict.endpoints[1].id),
                resolution=conflict.metadata.get("resolution") if conflict.metadata else None,
                timestamp=conflict.metadata.get("timestamp") if conflict.metadata else None,
                metadata=conflict.metadata,
            )
        return state_store.save_state(next_state, base_dir)

    def _run_preconnect(self, command: str, env_overrides: dict[str, str]) -> None:
        logger.info("Running SSH pre-connect command.")
        env = {**os.environ, **env_overrides}
        try:
            result = subprocess.run(
                command,
                shell=True,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise RuntimeError(f"Failed to execute pre-connect command: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(f"Pre-connect command failed: {result.stderr.strip() or result.stdout.strip()}")

    @staticmethod
    def _log_plan(plan_result: planner.PlannerOutput) -> None:
        logger.info(
            "Plan summary: %d operation(s), %d conflict(s).",
            len(plan_result.operations),
            len(plan_result.conflicts),
        )
        for op in plan_result.operations:
            src = op.source.id if op.source else "-"
            dst = op.destination.id if op.destination else "-"
            logger.info(" - %s %s (%s -> %s)", op.type.value, op.path, src, dst)
        for conflict in plan_result.conflicts:
            logger.error(
                " - Conflict at %s between %s and %s (%s)",
                conflict.path,
                conflict.endpoints[0].id,
                conflict.endpoints[1].id,
                conflict.reason,
            )


class InitWizard:
    """Interactive profile creation."""

    def __init__(self, *, config_dir: Optional[str] = None, input_func: Callable[[str], str] | None = None):
        self._config_dir = Path(config_dir).expanduser() if config_dir else None
        self._input = input_func or input

    def run(self, provided_name: Optional[str]) -> Path:
        base = config.ensure_config_structure(self._config_dir)
        name = provided_name or self._prompt("Profile name", default="new-profile")
        description = self._prompt("Description", default=f"{name} profile")
        endpoints = [
            self._prompt_endpoint(default_name="local", default_type="local"),
            self._prompt_endpoint(default_name="remote", default_type="ssh"),
        ]
        use_default_ignore = self._confirm(
            "Include default ignore patterns (.git, node_modules, __pycache__)?", default=True
        )
        ignore_block = config.IgnoreBlock(patterns=DEFAULT_IGNORE_PATTERNS if use_default_ignore else [])

        ssh_block = config.SshBlock(ssh_command="ssh") if any(ep.type == "ssh" for ep in endpoints) else None
        profile_cfg = config.ProfileConfig(
            profile=config.ProfileBlock(name=name, description=description),
            endpoints={ep.name: ep for ep in endpoints},
            conflict=config.ConflictBlock(policy="newest"),
            ignore=ignore_block,
            schedule=config.ScheduleBlock(),
            ssh=ssh_block,
        )
        toml_text = config.profile_to_toml(profile_cfg)
        target = base / "profiles" / f"{name}.toml"
        if target.exists():
            if not self._confirm(f"Profile '{name}' already exists. Overwrite?", default=False):
                raise config.ConfigError(f"Refused to overwrite existing profile '{name}'.")
        target.write_text(toml_text)
        return target

    def _prompt_endpoint(self, *, default_name: str, default_type: str) -> config.EndpointBlock:
        name = self._prompt(f"Endpoint name ({default_name})", default=default_name)
        endpoint_type = self._prompt_type(name, default_type)
        if endpoint_type == "local":
            path = self._prompt(f"Local path for '{name}'")
            absolute_path = str(Path(path).expanduser().resolve())
            return config.EndpointBlock(name=name, type="local", path=absolute_path)
        host = self._prompt(f"SSH host for '{name}'")
        path = self._prompt(f"Remote path for '{name}'")
        return config.EndpointBlock(name=name, type="ssh", host=host, path=path)

    def _prompt_type(self, name: str, default_type: str) -> str:
        while True:
            value = self._prompt(f"Endpoint '{name}' type [local/ssh]", default=default_type).lower()
            if value in {"local", "ssh"}:
                return value
            logger.warning("Please enter 'local' or 'ssh'.")

    def _prompt(self, message: str, *, default: Optional[str] = None) -> str:
        prompt_text = f"{message}"
        if default:
            prompt_text += f" [{default}]"
        prompt_text += ": "
        while True:
            response = self._input(prompt_text).strip()
            if response:
                return response
            if default is not None:
                return default
            logger.warning("This field is required.")

    def _confirm(self, message: str, *, default: bool) -> bool:
        suffix = "Y/n" if default else "y/N"
        prompt_text = f"{message} ({suffix}): "
        while True:
            response = self._input(prompt_text).strip().lower()
            if not response:
                return default
            if response in {"y", "yes"}:
                return True
            if response in {"n", "no"}:
                return False
            logger.warning("Please answer yes or no.")


@dataclass
class ProfileSummary:
    """Short summary of an on-disk profile."""

    name: str
    description: str
    path: Path
    last_sync: Optional[str] = None
    conflict_count: Optional[int] = None


def _gather_profile_summaries(config_dir_arg: Optional[str], *, include_conflicts: bool = False) -> List[ProfileSummary]:
    base = config.ensure_config_structure(Path(config_dir_arg).expanduser() if config_dir_arg else None)
    profiles_dir = base / "profiles"
    summaries: List[ProfileSummary] = []
    for path in sorted(profiles_dir.glob("*.toml")):
        try:
            profile = config.load_profile_from_path(path)
        except config.ConfigError as exc:
            logger.error("Skipping %s: %s", path.name, exc)
            continue
        state_path = _state_file_path(base, profile.profile.name)
        last_sync = _format_timestamp(state_path.stat().st_mtime) if state_path.exists() else None
        conflict_count: Optional[int] = None
        if include_conflicts and state_path.exists():
            try:
                state = state_store.load_state(profile.profile.name, base)
            except state_store.StateStoreError as exc:
                logger.error("Failed to read state for %s: %s", profile.profile.name, exc)
            else:
                conflict_count = len(state.conflicts)
        summaries.append(
            ProfileSummary(
                name=profile.profile.name,
                description=profile.profile.description,
                path=path,
                last_sync=last_sync,
                conflict_count=conflict_count,
            )
        )
    return summaries


def _print_profile_table(summaries: List[ProfileSummary], *, show_details: bool) -> None:
    headers = ["Name", "Description", "Last Sync"]
    if show_details:
        headers.append("File")
    rows: List[List[str]] = []
    for entry in summaries:
        row = [entry.name, entry.description, entry.last_sync or "never"]
        if show_details:
            row.append(str(entry.path))
        rows.append(row)
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    header_line = "  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    print(header_line)
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(row[idx].ljust(widths[idx]) for idx in range(len(headers))))


def _print_status_table(summaries: List[ProfileSummary]) -> None:
    headers = ["Name", "Last Sync", "Conflicts"]
    rows: List[List[str]] = []
    for entry in summaries:
        rows.append(
            [
                entry.name,
                entry.last_sync or "never",
                str(entry.conflict_count if entry.conflict_count is not None else 0),
            ]
        )
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    header_line = "  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    print(header_line)
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(row[idx].ljust(widths[idx]) for idx in range(len(headers))))


def _state_file_path(base: Path, profile_name: str) -> Path:
    safe_name = profile_name.replace("/", "_")
    return base / "state" / f"{safe_name}.json"


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for console_scripts."""
    parser = build_parser()

    # Enable argcomplete if available
    if ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)

    args = parser.parse_args(list(argv) if argv is not None else None)
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    handler: Handler = getattr(args, "func")
    return handler(args)


if __name__ == "__main__":  # pragma: no cover - manual execution guard
    raise SystemExit(main())
