# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "src" / "ProstoKVNNetwork.pyw"


class GuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GUI_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _app_class(self) -> ast.ClassDef:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "App":
                return node
        self.fail("Класс App не найден")

    def _method(self, name: str) -> ast.FunctionDef:
        for node in self._app_class().body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"Метод App.{name} не найден")

    def test_app_uses_ui_mixins(self):
        names = [base.id for base in self._app_class().bases if isinstance(base, ast.Name)]
        self.assertIn("ThemeMixin", names)
        self.assertIn("SubscriptionMixin", names)

    def test_runner_uses_new_api(self):
        method = self._method("_build_runner")
        text = ast.get_source_segment(self.source, method) or ""
        self.assertIn("custom_vpn_processes", text)
        self.assertNotIn("force_game_vpn", text)
        self.assertNotIn("discord_mode", text)

    def test_watchdog_is_present(self):
        self._method("_poll_runner_health")
        self.assertIn("self.after(1800, self._poll_runner_health)", self.source)

    def test_old_mixed_status_is_removed(self):
        self.assertNotIn("mixed:10808", self.source)
        self.assertIn("TUN: system · MTU 1400", self.source)


if __name__ == "__main__":
    unittest.main()
