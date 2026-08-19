# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui.dashboard import build_dashboard
from ui.settings_window import SettingsMixin
from ui.theme import ThemeMixin


class DashboardIntegrationTests(unittest.TestCase):
    def test_theme_keeps_settings_mixin(self):
        self.assertTrue(issubclass(ThemeMixin, SettingsMixin))

    def test_dashboard_builder_is_exposed(self):
        self.assertTrue(callable(build_dashboard))

    def test_dashboard_preserves_core_widget_contract(self):
        source = (ROOT / "src" / "ui" / "dashboard.py").read_text(encoding="utf-8")
        for attribute in (
            "app.test_btn",
            "app.start_btn",
            "app.stop_btn",
            "app.apply_btn",
            "app.tree",
            "app.logbox",
            "app.subscription_info",
            "app.bottom_right",
        ):
            self.assertIn(attribute, source)

    def test_dashboard_keeps_existing_tree_columns(self):
        source = (ROOT / "src" / "ui" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn('(\"name\", \"type\", \"ping\", \"udp\", \"status\")', source)


if __name__ == "__main__":
    unittest.main()
