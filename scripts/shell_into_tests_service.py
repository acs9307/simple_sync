#!/usr/bin/env python3
"""Open an interactive shell inside the docker-compose tests service."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from typing import List


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drop into an interactive bash session inside the tests service container."
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild of the tests image before starting the shell.",
    )
    args = parser.parse_args(argv)

    commands: List[List[str]] = []
    if args.rebuild:
        commands.append(["docker", "compose", "build", "tests"])
    commands.append(["docker", "compose", "run", "--rm", "--entrypoint", "/bin/bash", "tests"])

    for cmd in commands:
        pretty = " ".join(shlex.quote(part) for part in cmd)
        print(f"Running: {pretty}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
