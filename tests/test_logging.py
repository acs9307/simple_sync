"""Tests for the logging helper module."""

from __future__ import annotations

import io
import logging
import unittest

from simple_sync.logging import configure_logging


class TestConfigureLogging(unittest.TestCase):
    """Validate log level and destination behavior."""

    def setUp(self) -> None:
        logging.getLogger().handlers.clear()

    def test_verbose_enables_debug(self):
        sink = io.StringIO()
        configure_logging(verbose=1, stream=sink)
        logging.getLogger("simple_sync.test").debug("debug message")
        self.assertIn("debug message", sink.getvalue())

    def test_quiet_suppresses_info_but_not_warning(self):
        sink = io.StringIO()
        configure_logging(quiet=1, stream=sink)
        logger = logging.getLogger("simple_sync.test")
        logger.info("info message")
        self.assertEqual("", sink.getvalue())
        logger.warning("warning message")
        self.assertIn("warning message", sink.getvalue())


if __name__ == "__main__":
    unittest.main()
