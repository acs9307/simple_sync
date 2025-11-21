"""PyInstaller entrypoint that imports the real CLI from the package."""

from simple_sync.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
