from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from simple_sync import versioning


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "README.md").write_text("demo")
    _git(repo, "add", "README.md")
    _git(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test User",
        "commit",
        "-m",
        "init",
    )
    return repo


def test_latest_version_tag_picks_highest_semver(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.1.0")
    _git(repo, "tag", "v0.2.0")
    _git(repo, "tag", "v0.1.5")

    assert versioning.latest_version_tag(repo) == "v0.2.0"
    assert versioning.resolve_version_from_tags(repo) == "0.2.0"


def test_version_from_tag_rejects_invalid_format() -> None:
    with pytest.raises(versioning.VersionError):
        versioning.version_from_tag("0.1.0")
    with pytest.raises(versioning.VersionError):
        versioning.version_from_tag("v1.2")


def test_update_version_files_writes_pyproject_and_init(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    init_file = tmp_path / "__init__.py"

    pyproject.write_text(
        "\n".join(
            [
                "[project]",
                'name = "simple-sync"',
                'version = "0.0.0"',
                "",
            ]
        )
    )
    init_file.write_text('__version__ = "0.0.0"\n')

    versioning.update_version_files("1.2.3", pyproject_path=pyproject, init_path=init_file)

    assert 'version = "1.2.3"' in pyproject.read_text()
    assert '__version__ = "1.2.3"' in init_file.read_text()


def test_update_version_files_errors_when_missing_fields(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    init_file = tmp_path / "__init__.py"
    pyproject.write_text("[project]\nname = \"simple-sync\"\n")
    init_file.write_text("# missing version\n")

    with pytest.raises(versioning.VersionError):
        versioning.update_version_files("1.0.0", pyproject_path=pyproject, init_path=init_file)


def test_tag_commit_resolves_tag_hash(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.0.1")
    commit = versioning.tag_commit("v0.0.1", repo)
    assert len(commit) == 40


def test_update_formula_rewrites_version_and_revision(tmp_path: Path) -> None:
    formula = tmp_path / "simple-sync.rb"
    formula.write_text(
        "\n".join(
            [
                'url "https://github.com/acs9307/simple_sync.git",',
                '    revision: "oldrev"',
                'version "0.0.0"',
            ]
        )
    )
    versioning.update_formula(formula_path=formula, version="1.2.3", revision="abc123")
    text = formula.read_text()
    assert 'revision: "abc123"' in text
    assert 'version "1.2.3"' in text
