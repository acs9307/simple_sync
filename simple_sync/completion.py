"""Tab completion support for simple-sync CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from . import config


def profile_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs) -> Iterable[str]:
    """
    Complete profile names from the user's configuration directory.

    Args:
        prefix: The current partial profile name being typed
        parsed_args: Parsed arguments so far
        **kwargs: Additional context from argcomplete

    Returns:
        List of matching profile names
    """
    try:
        # Get config directory
        config_dir_arg = getattr(parsed_args, 'config_dir', None)
        if config_dir_arg:
            base = Path(config_dir_arg).expanduser()
        else:
            base = config.get_base_config_dir()

        # Ensure profiles directory exists
        profiles_dir = base / "profiles"
        if not profiles_dir.exists():
            return []

        # Get all profile names (without .toml extension)
        profile_names = []
        for profile_path in profiles_dir.glob("*.toml"):
            name = profile_path.stem
            if name.startswith(prefix):
                profile_names.append(name)

        return sorted(profile_names)
    except Exception:
        # If anything goes wrong, return empty list
        return []


def endpoint_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs) -> Iterable[str]:
    """
    Complete endpoint names from the specified profile.

    Args:
        prefix: The current partial endpoint name being typed
        parsed_args: Parsed arguments so far
        **kwargs: Additional context from argcomplete

    Returns:
        List of matching endpoint names
    """
    try:
        profile_name = getattr(parsed_args, 'profile', None)
        if not profile_name:
            return []

        config_dir_arg = getattr(parsed_args, 'config_dir', None)
        if config_dir_arg:
            base = Path(config_dir_arg).expanduser()
        else:
            base = None

        # Load the profile
        profile_cfg = config.load_profile(profile_name, base)

        # Get endpoint names
        endpoint_names = [
            name for name in profile_cfg.endpoints.keys()
            if name.startswith(prefix)
        ]

        return sorted(endpoint_names)
    except Exception:
        # If profile doesn't exist or can't be loaded, return empty list
        return []


def policy_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs) -> Iterable[str]:
    """
    Complete conflict policy names.

    Args:
        prefix: The current partial policy name being typed
        parsed_args: Parsed arguments so far
        **kwargs: Additional context from argcomplete

    Returns:
        List of matching policy names
    """
    policies = ["newest", "prefer", "manual"]
    return [p for p in policies if p.startswith(prefix)]


def endpoint_type_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs) -> Iterable[str]:
    """
    Complete endpoint type names.

    Args:
        prefix: The current partial type name being typed
        parsed_args: Parsed arguments so far
        **kwargs: Additional context from argcomplete

    Returns:
        List of matching endpoint types
    """
    types = ["local", "ssh"]
    return [t for t in types if t.startswith(prefix)]


def directory_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs) -> Iterable[str]:
    """
    Complete directory paths.

    Args:
        prefix: The current partial path being typed
        parsed_args: Parsed arguments so far
        **kwargs: Additional context from argcomplete

    Returns:
        List of matching directory paths
    """
    try:
        import os
        from argcomplete.completers import DirectoriesCompleter

        # Use argcomplete's built-in directory completer
        completer = DirectoriesCompleter()
        return completer(prefix, parsed_args, **kwargs)
    except Exception:
        return []


__all__ = [
    "profile_completer",
    "endpoint_completer",
    "policy_completer",
    "endpoint_type_completer",
    "directory_completer",
]
