# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import queue
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import Node
from ui.runtime_safety import _discard_pending_vpn_events, best_working_node


class RuntimeSafetyTests(unittest.TestCase):
    def node(self, name: str, *, valid: bool, https_ms: float | None, score: float) -> Node:
        return Node(
            name=name,
            protocol="trojan",
            server="example.com",
            port=443,
            outbound={"type": "trojan"},
            valid=valid,
            https_ms=https_ms,
            score=score,
        )

    def test_no_failed_node_is_selected_as_best(self):
        tested = [
            self.node("invalid", valid=False, https_ms=None, score=9999),
            self.node("https-fail", valid=True, https_ms=None, score=5000),
        ]
        self.assertIsNone(best_working_node(tested))

    def test_best_working_node_ignores_invalid_high_score(self):
        tested = [
            self.node("invalid", valid=False, https_ms=20, score=9999),
            self.node("good-a", valid=True, https_ms=80, score=500),
            self.node("good-b", valid=True, https_ms=70, score=700),
        ]
        self.assertEqual(best_working_node(tested).name, "good-b")

    def test_stale_vpn_events_are_removed(self):
        class App:
            events = queue.Queue()

        app = App()
        app.events.put(("started", ("smart_ru", None)))
        app.events.put(("row", "node"))
        app.events.put(("stopped", None))
        _discard_pending_vpn_events(app)

        self.assertEqual(app.events.get_nowait(), ("row", "node"))
        with self.assertRaises(queue.Empty):
            app.events.get_nowait()

    def test_runtime_safety_is_installed_before_dashboard(self):
        source = (ROOT / "src" / "ui" / "theme.py").read_text(encoding="utf-8")
        install_pos = source.index("install_runtime_safety(self)")
        dashboard_pos = source.index("build_dashboard(self)", install_pos)
        self.assertLess(install_pos, dashboard_pos)


if __name__ == "__main__":
    unittest.main()
