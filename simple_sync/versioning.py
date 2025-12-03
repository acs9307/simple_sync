"""Release version helpers sourced from git tags."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

VERSION_TAG_PATTERN = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


class VersionError(RuntimeError):
    """Raised when release version discovery or updates fail."""

    pass


def latest_version_tag(repo_path: Path | str = ".") -> str:
    """
    Return the latest version tag (vMAJOR.MINOR.PATCH) in the repository.

    Raises VersionError if no matching tags are found.
    """
    repo = Path(repo_path)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "tag", "--list", "v[0-9]*.[0-9]*.[0-9]*"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - git missing is environment-specific
        raise VersionError(f"Failed to read git tags: {exc}") from exc

    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    matching = [tag for tag in tags if VERSION_TAG_PATTERN.match(tag)]
    if not matching:
        raise VersionError("No tags matching vMAJOR.MINOR.PATCH were found.")

    def _version_tuple(tag: str) -> tuple[int, int, int]:
        match = VERSION_TAG_PATTERN.match(tag)
        assert match  # already validated above
        return tuple(int(part) for part in match.groups())

    return sorted(matching, key=_version_tuple, reverse=True)[0]


def version_from_tag(tag: str) -> str:
    """Convert a tag like v0.1.2 to a plain version string."""
    match = VERSION_TAG_PATTERN.match(tag)
    if not match:
        raise VersionError(f"Tag '{tag}' does not match vMAJOR.MINOR.PATCH.")
    major, minor, patch = match.groups()
    return f"{major}.{minor}.{patch}"


def update_version_files(
    version: str,
    *,
    pyproject_path: Path,
    init_path: Path,
    dry_run: bool = False,
) -> None:
    """
    Write the resolved version into pyproject.toml and simple_sync/__init__.py.

    Raises VersionError if the expected fields are missing.
    """
    pyproject_text = pyproject_path.read_text()
    init_text = init_path.read_text()

    pyproject_updated, pyproject_count = re.subn(
        r'(?m)^(version\s*=\s*)"[^"]+"', rf'\1"{version}"', pyproject_text, count=1
    )
    if pyproject_count == 0:
        raise VersionError("Could not find version field in pyproject.toml.")

    init_updated, init_count = re.subn(
        r'(?m)^(__version__\s*=\s*)"[^"]+"', rf'\1"{version}"', init_text, count=1
    )
    if init_count == 0:
        raise VersionError("Could not find __version__ in __init__.py.")

    if dry_run:
        return

    pyproject_path.write_text(pyproject_updated)
    init_path.write_text(init_updated)


def resolve_version_from_tags(repo_path: Path | str = ".") -> str:
    """Resolve the latest git tag to a plain version string."""
    tag = latest_version_tag(repo_path)
    return version_from_tag(tag)


def tag_commit(tag: str, repo_path: Path | str = ".") -> str:
    """Return the commit hash for a given tag."""
    repo = Path(repo_path)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", tag],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - environment dependent
        raise VersionError(f"Failed to resolve commit for tag {tag}: {exc}") from exc
    return result.stdout.strip()


def update_formula(
    *,
    formula_path: Path,
    version: str,
    revision: str,
    url: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Update a Homebrew formula with the provided version and revision.

    Optionally updates the source URL when provided.
    """
    text = formula_path.read_text()

    if url:
        text, url_count = re.subn(
            r'(?m)^(url\s*")([^"]+)(")',
            rf'\1{url}\3',
            text,
            count=1,
        )
        if url_count == 0:
            raise VersionError("Could not find url field in formula.")

    def _replace_revision(match: re.Match[str]) -> str:
        return f'{match.group(1)}{revision}{match.group(3)}'

    text, rev_count = re.subn(
        r'(?m)(revision:\s*")([^"]+)(")',
        _replace_revision,
        text,
        count=1,
    )
    if rev_count == 0:
        raise VersionError("Could not find revision field in formula.")

    def _replace_version(match: re.Match[str]) -> str:
        return f'{match.group(1)}{version}{match.group(3)}'

    text, ver_count = re.subn(
        r'(?m)^\s*(version\s*")([^"]+)(")',
        _replace_version,
        text,
        count=1,
    )
    if ver_count == 0:
        raise VersionError("Could not find version field in formula.")

    if dry_run:
        return
    formula_path.write_text(text)
