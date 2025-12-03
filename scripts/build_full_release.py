#!/usr/bin/env python
"""Build release artifacts (Python packages + Homebrew formula) from the latest tag."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Ensure repo root import
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simple_sync import versioning  # noqa: E402


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {result.stderr.strip() or result.stdout.strip()}")
    return result


def build_release(repo: Path, dist_dir: Path) -> None:
    tag = versioning.latest_version_tag(repo)
    version = versioning.version_from_tag(tag)
    revision = versioning.tag_commit(tag, repo)

    pyproject_path = repo / "pyproject.toml"
    init_path = repo / "simple_sync" / "__init__.py"
    versioning.update_version_files(version, pyproject_path=pyproject_path, init_path=init_path)

    formula_path = repo / "Formula" / "simple-sync.rb"
    if formula_path.exists():
        versioning.update_formula(formula_path=formula_path, version=version, revision=revision)

    dist_dir.mkdir(parents=True, exist_ok=True)

    _run([sys.executable, "-m", "build", "--outdir", str(dist_dir)], cwd=repo)

    archive_path = dist_dir / f"simple-sync-{tag}.tar.gz"
    _run(
        [
            "git",
            "-C",
            str(repo),
            "archive",
            "--format=tar.gz",
            f"--prefix=simple_sync-{version}/",
            "-o",
            str(archive_path),
            tag,
        ],
        cwd=repo,
    )

    print(f"Release version: {version} (tag {tag}, revision {revision})")
    print(f"Built Python artifacts under {dist_dir}")
    print(f"Created source archive for Homebrew: {archive_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build full release artifacts from latest tag.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Path to repository root (default: project root).",
    )
    parser.add_argument(
        "--dist",
        type=Path,
        default=None,
        help="Output directory for artifacts (default: <repo>/dist).",
    )
    args = parser.parse_args()

    repo = args.repo.resolve()
    dist_dir = (args.dist or (repo / "dist")).resolve()

    try:
        build_release(repo, dist_dir)
    except versioning.VersionError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
