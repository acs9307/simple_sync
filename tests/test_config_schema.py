"""Schema-related tests for config dataclasses and examples."""

from __future__ import annotations

import unittest
from pathlib import Path

from simple_sync import config


class TestProfileTemplate(unittest.TestCase):
    def test_template_contains_expected_sections(self):
        template = config.build_profile_template()
        self.assertEqual(template.profile.topology, "pair")
        self.assertIn("local", template.endpoints)
        self.assertIn("remote", template.endpoints)
        self.assertTrue(template.ignore.patterns)
        self.assertEqual(template.schedule.interval_seconds, 3600)
        self.assertEqual(template.conflict.policy, "newest")
        self.assertIsNotNone(template.ssh)

    def test_profile_to_toml_serializes_sections(self):
        template = config.build_profile_template()
        toml_text = config.profile_to_toml(template)
        self.assertIn("[profile]", toml_text)
        self.assertIn("[conflict]", toml_text)
        self.assertIn("[endpoints.local]", toml_text)


class TestExampleToml(unittest.TestCase):
    def test_example_file_lists_expected_sections(self):
        text = Path("examples/profile.example.toml").read_text()
        for section in [
            "[profile]",
            "[conflict]",
            "[ignore]",
            "[schedule]",
            "[ssh]",
            "[endpoints.local]",
            "[endpoints.remote]",
        ]:
            self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
