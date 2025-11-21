"""Configuration path helpers."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

CONFIG_DIR_NAME = "simple_sync"
SUBDIRECTORIES: tuple[str, ...] = ("profiles", "state", "logs")


def is_windows() -> bool:
    """Return True if running on Windows."""
    return os.name == "nt" or sys.platform.startswith("win")


def get_base_config_dir() -> Path:
    """Resolve the platform-specific configuration directory."""
    if is_windows():
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / CONFIG_DIR_NAME
    return Path.home() / ".config" / CONFIG_DIR_NAME


def ensure_config_structure(base_dir: Path | None = None, *, subdirs: Iterable[str] = SUBDIRECTORIES) -> Path:
    """Ensure that the config directory and expected subdirectories exist."""
    base = base_dir or get_base_config_dir()
    base.mkdir(parents=True, exist_ok=True)
    for name in subdirs:
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


class ConfigError(RuntimeError):
    """Raised when a configuration file is invalid."""

    pass


@dataclass
class ProfileBlock:
    """Metadata about the profile itself."""

    name: str
    description: str
    topology: str = "pair"


@dataclass
class EndpointBlock:
    """Endpoint definition supporting local and ssh targets."""

    name: str
    type: str
    path: Optional[str] = None
    host: Optional[str] = None
    description: Optional[str] = None
    ssh_command: Optional[str] = None
    pre_connect_command: Optional[str] = None


@dataclass
class ConflictBlock:
    policy: str
    prefer: Optional[str] = None
    manual_behavior: Optional[str] = None


@dataclass
class IgnoreBlock:
    patterns: List[str] = field(default_factory=list)


@dataclass
class ScheduleBlock:
    enabled: bool = False
    interval_seconds: int = 3600
    run_on_start: bool = True


@dataclass
class SshBlock:
    pre_connect_command: Optional[str] = None
    ssh_command: Optional[str] = None
    use_agent: bool = True
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class ProfileConfig:
    """Complete config document representation."""

    profile: ProfileBlock
    endpoints: Dict[str, EndpointBlock]
    conflict: ConflictBlock
    ignore: IgnoreBlock = field(default_factory=IgnoreBlock)
    schedule: ScheduleBlock = field(default_factory=ScheduleBlock)
    ssh: Optional[SshBlock] = None


def build_profile_template() -> ProfileConfig:
    """Return an in-memory template with sensible defaults."""
    profile = ProfileBlock(name="example", description="Example profile.")
    endpoints = {
        "local": EndpointBlock(name="local", type="local", path="~/projects/example"),
        "remote": EndpointBlock(name="remote", type="ssh", host="example.com", path="/srv/data/example"),
    }
    conflict = ConflictBlock(policy="newest", prefer="local", manual_behavior="copy_both")
    ignore = IgnoreBlock(patterns=[".git", "node_modules", "__pycache__"])
    schedule = ScheduleBlock(enabled=False, interval_seconds=3600, run_on_start=True)
    ssh_block = SshBlock(pre_connect_command=None, ssh_command="ssh", use_agent=True, env={})
    return ProfileConfig(
        profile=profile,
        endpoints=endpoints,
        conflict=conflict,
        ignore=ignore,
        schedule=schedule,
        ssh=ssh_block,
    )


def profile_to_toml(profile: ProfileConfig) -> str:
    """Serialize a ProfileConfig back to TOML text."""
    lines: List[str] = []

    def add_section(header: str, fields: Dict[str, Any]) -> None:
        if not fields:
            return
        lines.append(header)
        for key, value in fields.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")

    add_section(
        "[profile]",
        {
            "name": profile.profile.name,
            "description": profile.profile.description,
            "topology": profile.profile.topology,
        },
    )
    add_section(
        "[conflict]",
        {
            "policy": profile.conflict.policy,
            **({"prefer": profile.conflict.prefer} if profile.conflict.prefer else {}),
            **(
                {"manual_behavior": profile.conflict.manual_behavior}
                if profile.conflict.manual_behavior
                else {}
            ),
        },
    )
    add_section("[ignore]", {"patterns": profile.ignore.patterns})
    add_section(
        "[schedule]",
        {
            "enabled": profile.schedule.enabled,
            "interval_seconds": profile.schedule.interval_seconds,
            "run_on_start": profile.schedule.run_on_start,
        },
    )
    if profile.ssh:
        add_section(
            "[ssh]",
            {
                "use_agent": profile.ssh.use_agent,
                **(
                    {"pre_connect_command": profile.ssh.pre_connect_command}
                    if profile.ssh.pre_connect_command
                    else {}
                ),
                **({"ssh_command": profile.ssh.ssh_command} if profile.ssh.ssh_command else {}),
            },
        )
        if profile.ssh.env:
            add_section(
                "[ssh.env]",
                {key: value for key, value in profile.ssh.env.items()},
            )

    for name, endpoint in profile.endpoints.items():
        header = f"[endpoints.{name}]"
        fields: Dict[str, Any] = {"type": endpoint.type}
        if endpoint.path:
            fields["path"] = endpoint.path
        if endpoint.host:
            fields["host"] = endpoint.host
        if endpoint.description:
            fields["description"] = endpoint.description
        if endpoint.ssh_command:
            fields["ssh_command"] = endpoint.ssh_command
        if endpoint.pre_connect_command:
            fields["pre_connect_command"] = endpoint.pre_connect_command
        add_section(header, fields)

    content = "\n".join(lines).strip()
    return content + ("\n" if content else "")


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + escaped + '"'
    if isinstance(value, list):
        inner = ", ".join(_format_value(item) for item in value)
        return f"[{inner}]"
    raise TypeError(f"Unsupported TOML value: {value!r}")


def load_profile(profile_name: str, base_dir: Path | None = None) -> ProfileConfig:
    """Load and validate a profile file from the config directory."""
    base = ensure_config_structure(base_dir)
    profile_path = base / "profiles" / f"{profile_name}.toml"
    if not profile_path.exists():
        raise ConfigError(f"Profile '{profile_name}' not found at {profile_path}.")
    return load_profile_from_path(profile_path)


def load_profile_from_path(profile_path: Path) -> ProfileConfig:
    """Load a profile from an explicit path."""
    try:
        raw_data = profile_path.read_text()
    except OSError as exc:  # pragma: no cover - filesystem errors
        raise ConfigError(f"Unable to read profile file {profile_path}: {exc}") from exc

    try:
        mapping = _parse_toml(raw_data)
    except ValueError as exc:
        raise ConfigError(f"Failed to parse {profile_path.name}: {exc}") from exc

    return _build_profile_config(mapping, profile_path)


def _build_profile_config(data: Mapping[str, Any], profile_path: Path) -> ProfileConfig:
    profile_block = _load_profile_block(_require_table(data, "profile"), profile_path)
    endpoints = _load_endpoints(_require_table(data, "endpoints"), profile_path)
    conflict = _load_conflict(_require_table(data, "conflict"), profile_path)
    if conflict.policy == "prefer" and conflict.prefer not in endpoints:
        raise ConfigError(
            f"Conflict prefer endpoint '{conflict.prefer}' not defined in endpoints for {profile_path}."
        )
    ignore = _load_ignore(data.get("ignore"))
    schedule = _load_schedule(data.get("schedule"))
    ssh_block = _load_ssh(data.get("ssh"))
    return ProfileConfig(
        profile=profile_block,
        endpoints=endpoints,
        conflict=conflict,
        ignore=ignore,
        schedule=schedule,
        ssh=ssh_block,
    )


def _load_profile_block(block: Mapping[str, Any], profile_path: Path) -> ProfileBlock:
    name = _require_str(block, "name", "[profile]", profile_path)
    description = _require_str(block, "description", "[profile]", profile_path)
    topology = block.get("topology", "pair")
    if topology != "pair":
        raise ConfigError(f"Unsupported topology '{topology}' in {profile_path}.")
    return ProfileBlock(name=name, description=description, topology=topology)


def _load_endpoints(block: Mapping[str, Any], profile_path: Path) -> Dict[str, EndpointBlock]:
    if not block:
        raise ConfigError(f"At least one endpoint must be defined in {profile_path}.")
    endpoints: Dict[str, EndpointBlock] = {}
    for name, value in block.items():
        if not isinstance(value, Mapping):
            raise ConfigError(f"Endpoint '{name}' must be a table in {profile_path}.")
        endpoint_type = _require_str(value, "type", f"[endpoints.{name}]", profile_path)
        path = value.get("path")
        host = value.get("host")
        if endpoint_type not in {"local", "ssh"}:
            raise ConfigError(
                f"Endpoint '{name}' has unsupported type '{endpoint_type}' in {profile_path}."
            )
        if endpoint_type == "local" and not path:
            raise ConfigError(f"Endpoint '{name}' (local) must define 'path' in {profile_path}.")
        if endpoint_type == "ssh":
            if not host:
                raise ConfigError(f"Endpoint '{name}' (ssh) must define 'host' in {profile_path}.")
            if not path:
                raise ConfigError(f"Endpoint '{name}' (ssh) must define 'path' in {profile_path}.")
        endpoints[name] = EndpointBlock(
            name=name,
            type=endpoint_type,
            path=path,
            host=host,
            description=value.get("description"),
            ssh_command=value.get("ssh_command"),
            pre_connect_command=value.get("pre_connect_command"),
        )
    return endpoints


def _load_conflict(block: Mapping[str, Any], profile_path: Path) -> ConflictBlock:
    policy = _require_str(block, "policy", "[conflict]", profile_path)
    prefer = block.get("prefer")
    manual_behavior = block.get("manual_behavior")
    if policy not in {"newest", "prefer", "manual"}:
        raise ConfigError(f"Conflict policy '{policy}' is not supported in {profile_path}.")
    if policy == "prefer" and not prefer:
        raise ConfigError(f"'prefer' policy requires 'prefer' field in {profile_path}.")
    if policy == "manual" and not manual_behavior:
        raise ConfigError(f"'manual' policy requires 'manual_behavior' field in {profile_path}.")
    return ConflictBlock(policy=policy, prefer=prefer, manual_behavior=manual_behavior)


def _load_ignore(block: Any) -> IgnoreBlock:
    if not block:
        return IgnoreBlock()
    patterns = block.get("patterns", [])
    if not isinstance(patterns, list):
        raise ConfigError("ignore.patterns must be an array of strings.")
    str_patterns = []
    for pattern in patterns:
        if not isinstance(pattern, str):
            raise ConfigError("ignore.patterns must only contain strings.")
        str_patterns.append(pattern)
    return IgnoreBlock(patterns=str_patterns)


def _load_schedule(block: Any) -> ScheduleBlock:
    if not block:
        return ScheduleBlock()
    enabled = bool(block.get("enabled", False))
    interval = block.get("interval_seconds", 3600)
    run_on_start = bool(block.get("run_on_start", True))
    if not isinstance(interval, int) or interval <= 0:
        raise ConfigError("schedule.interval_seconds must be a positive integer.")
    return ScheduleBlock(enabled=enabled, interval_seconds=interval, run_on_start=run_on_start)


def _load_ssh(block: Any) -> Optional[SshBlock]:
    if not block:
        return SshBlock()
    env = block.get("env", {})
    if env and not isinstance(env, dict):
        raise ConfigError("ssh.env must be a table of key/value pairs.")
    return SshBlock(
        pre_connect_command=block.get("pre_connect_command"),
        ssh_command=block.get("ssh_command"),
        use_agent=bool(block.get("use_agent", True)),
        env={str(k): str(v) for k, v in env.items()},
    )


def _require_table(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ConfigError(f"Section [{key}] is required.")
    return value


def _require_str(block: Mapping[str, Any], key: str, section: str, profile_path: Path) -> str:
    value = block.get(key)
    if not isinstance(value, str):
        raise ConfigError(f"{section} must define string '{key}' in {profile_path}.")
    return value


def _parse_toml(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    current_path: List[str] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            table_name = line[1:-1].strip()
            if not table_name:
                raise ValueError(f"Empty table name on line {lineno}.")
            current_path = [segment.strip() for segment in table_name.split(".")]
            _ensure_nested_table(result, current_path)
            continue
        if "=" not in line:
            raise ValueError(f"Expected 'key = value' on line {lineno}.")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Missing key on line {lineno}.")
        parsed_value = _parse_value(value.strip(), lineno)
        target = _resolve_table(result, current_path)
        if key in target:
            raise ValueError(f"Duplicate key '{key}' on line {lineno}.")
        target[key] = parsed_value
    return result


def _parse_value(raw_value: str, lineno: int) -> Any:
    value = _strip_inline_comment(raw_value)
    if not value:
        raise ValueError(f"Missing value on line {lineno}.")
    if value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return bytes(inner, "utf-8").decode("unicode_escape")
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value.startswith("[") and value.endswith("]"):
        return _parse_array(value[1:-1], lineno)
    if value.lstrip("+-").isdigit():
        return int(value)
    return value


def _parse_array(inner: str, lineno: int) -> List[Any]:
    if not inner.strip():
        return []
    items: List[Any] = []
    current = []
    in_string = False
    escape = False
    for ch in inner:
        if in_string:
            current.append(ch)
            if ch == '"' and not escape:
                in_string = False
            elif ch == "\\" and not escape:
                escape = True
                continue
            escape = False
            continue
        if ch == '"':
            in_string = True
            current.append(ch)
            continue
        if ch == ",":
            token = "".join(current).strip()
            if token:
                items.append(_parse_value(token, lineno))
            current = []
            continue
        current.append(ch)
    token = "".join(current).strip()
    if token:
        items.append(_parse_value(token, lineno))
    return items


def _strip_inline_comment(value: str) -> str:
    result = []
    in_string = False
    escape = False
    for ch in value:
        if ch == '"' and not escape:
            in_string = not in_string
        if ch == "#" and not in_string:
            break
        result.append(ch)
        if ch == "\\" and not escape:
            escape = True
            continue
        escape = False
    return "".join(result).strip()


def _ensure_nested_table(result: Dict[str, Any], path: List[str]) -> None:
    target = result
    for segment in path:
        if not segment:
            raise ValueError("Empty segment in table path.")
        target = target.setdefault(segment, {})
        if not isinstance(target, dict):
            raise ValueError(f"Cannot create table '{'.'.join(path)}' due to conflicting key.")


def _resolve_table(result: Dict[str, Any], path: List[str]) -> Dict[str, Any]:
    target: Dict[str, Any] = result
    for segment in path:
        value = target.setdefault(segment, {})
        if not isinstance(value, dict):
            raise ValueError(f"Cannot assign to non-table '{segment}'.")
        target = value
    return target


__all__ = [
    "ConfigError",
    "CONFIG_DIR_NAME",
    "ConflictBlock",
    "EndpointBlock",
    "IgnoreBlock",
    "ProfileBlock",
    "ProfileConfig",
    "ScheduleBlock",
    "SshBlock",
    "SUBDIRECTORIES",
    "build_profile_template",
    "ensure_config_structure",
    "get_base_config_dir",
    "is_windows",
    "load_profile",
    "load_profile_from_path",
    "profile_to_toml",
]
