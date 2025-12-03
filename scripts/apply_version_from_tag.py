#!/usr/bin/env python
"""Update project version fields from the latest git tag (vMAJOR.MINOR.PATCH)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is importable when executed as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simple_sync import versioning


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the latest git tag (vMAJOR.MINOR.PATCH) to project version files."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Path to the git repository root (default: project root).",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=None,
        help="Path to pyproject.toml (default: <repo>/pyproject.toml).",
    )
    parser.add_argument(
        "--init",
        type=Path,
        default=None,
        help="Path to simple_sync/__init__.py (default: <repo>/simple_sync/__init__.py).",
    )
    parser.add_argument(
        "--formula",
        type=Path,
        default=None,
        help="Optional path to Formula/simple-sync.rb to update alongside version files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and validate versions without writing files.",
    )
    args = parser.parse_args()

    repo = args.repo
    pyproject_path = args.pyproject or (repo / "pyproject.toml")
    init_path = args.init or (repo / "simple_sync" / "__init__.py")

    formula_path = args.formula or (repo / "Formula" / "simple-sync.rb")

    try:
        tag = versioning.latest_version_tag(repo)
        version = versioning.version_from_tag(tag)
        versioning.update_version_files(
            version,
            pyproject_path=pyproject_path,
            init_path=init_path,
            dry_run=args.dry_run,
        )
        if formula_path.exists():
            revision = versioning.tag_commit(tag, repo)
            versioning.update_formula(
                formula_path=formula_path,
                version=version,
                revision=revision,
                dry_run=args.dry_run,
            )
    except versioning.VersionError as exc:
        parser.error(str(exc))
    print(f"Set project version to {version} from latest tag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
