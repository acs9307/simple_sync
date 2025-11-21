"""Basic daemon runner for scheduled profile execution."""

from __future__ import annotations

import logging
import signal
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from simple_sync import config

logger = logging.getLogger(__name__)


@dataclass
class ScheduledProfile:
    name: str
    interval: int
    next_run: float


class DaemonRunner:
    def __init__(self, *, config_dir: Optional[str] = None):
        self._config_dir = Path(config_dir).expanduser() if config_dir else None
        self._base_dir = config.ensure_config_structure(self._config_dir)
        self._stop = False
        self._reload = False

    def run_forever(self, *, run_once: bool = False) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGHUP, self._handle_signal)
        profiles = self._load_scheduled_profiles()
        from simple_sync.cli import SyncRunner

        runner = SyncRunner(config_dir=self._config_dir)
        while not self._stop:
            if self._reload:
                logger.info("Reloading daemon profiles.")
                profiles = self._load_scheduled_profiles()
                self._reload = False
            now = time.time()
            due = [p for p in profiles.values() if p.next_run <= now]
            if due:
                for profile in due:
                    try:
                        with self._profile_logger(profile.name):
                            logger.info("Running scheduled sync for %s.", profile.name)
                            runner.run(profile_name=profile.name, dry_run=False)
                    except Exception as exc:  # pragma: no cover
                        logger.error("Scheduled sync failed: %s", exc)
                    profile.next_run = time.time() + profile.interval
                if run_once:
                    break
                continue
            if run_once:
                break
            if profiles:
                sleep_for = min(p.next_run for p in profiles.values()) - now
                time.sleep(max(sleep_for, 1))
            else:
                time.sleep(5)

    def _load_scheduled_profiles(self) -> Dict[str, ScheduledProfile]:
        summaries = _gather_profiles(self._base_dir)
        scheduled: Dict[str, ScheduledProfile] = {}
        for profile_cfg in summaries:
            if not profile_cfg.schedule.enabled:
                continue
            scheduled[profile_cfg.profile.name] = ScheduledProfile(
                name=profile_cfg.profile.name,
                interval=profile_cfg.schedule.interval_seconds,
                next_run=time.time(),
            )
        return scheduled

    def _handle_signal(self, signum, frame):  # pragma: no cover
        if signum == signal.SIGHUP:
            logger.info("Received SIGHUP; scheduling profile reload.")
            self._reload = True
            return
        logger.info("Received signal %s; shutting down daemon.", signum)
        self._stop = True

    @contextmanager
    def _profile_logger(self, profile_name: str):
        log_dir = self._base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / f"{profile_name}.log"
        handler = logging.FileHandler(file_path)
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            yield
        finally:
            root.removeHandler(handler)
            handler.close()


def _gather_profiles(base: Path):
    profiles = []
    profiles_dir = base / "profiles"
    for path in profiles_dir.glob("*.toml"):
        profiles.append(config.load_profile_from_path(path))
    return profiles
