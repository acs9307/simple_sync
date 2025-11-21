#!/usr/bin/env python3
"""Utility to run the test suite inside the Docker Compose harness."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from typing import List


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pytest inside the Docker Compose test harness.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild of the test image before running.",
    )
    parser.add_argument(
        "--pytest-args",
        default="",
        help="Extra arguments to pass through to pytest inside the container.",
    )
    args = parser.parse_args(argv)

    env = os.environ.copy()
    env["PYTEST_ARGS"] = args.pytest_args

    commands: List[List[str]] = []
    if args.rebuild:
        commands.append(["docker", "compose", "build", "tests"])
    commands.append(["docker", "compose", "run", "--rm", "tests"])

    for cmd in commands:
        pretty = " ".join(shlex.quote(part) for part in cmd)
        print(f"Running: {pretty}")
        result = subprocess.run(cmd, env=env)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
