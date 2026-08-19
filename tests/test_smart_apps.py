# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from routing import (
    UBISOFT_DOMAIN_SUFFIXES,
    UBISOFT_SMART_PROCESSES,
    build_route_rules,
    is_reserved_direct_process,
)


class SmartAppsTests(unittest.TestCase):
    def test_smart_has_ubisoft_profile(self):
        rules, _, final = build_route_rules("smart_ru")
        self.assertEqual(final, "direct")
        self.assertTrue(any(rule.get("process_name") == UBISOFT_SMART_PROCESSES and rule.get("outbound") == "proxy" for rule in rules))
        self.assertTrue(any(rule.get("domain_suffix") == UBISOFT_DOMAIN_SUFFIXES and rule.get("outbound") == "proxy" for rule in rules))

    def test_apps_mode_only_uses_manual_processes(self):
        rules, _, _ = build_route_rules("game_only", custom_vpn_processes=["client"])
        self.assertTrue(any(rule.get("process_name") == ["client.exe"] and rule.get("outbound") == "proxy" for rule in rules))
        self.assertFalse(any("Discord.exe" in rule.get("process_name", []) for rule in rules))
        self.assertFalse(any("Telegram.exe" in rule.get("process_name", []) for rule in rules))
        self.assertFalse(any(rule.get("process_name") == UBISOFT_SMART_PROCESSES for rule in rules))

    def test_ru_direct_is_before_manual_process(self):
        rules, _, _ = build_route_rules("smart_ru", custom_vpn_processes=["browser.exe"])
        ru_index = next(i for i, rule in enumerate(rules) if ".ru" in rule.get("domain_suffix", []))
        app_index = next(i for i, rule in enumerate(rules) if rule.get("process_name") == ["browser.exe"])
        self.assertLess(ru_index, app_index)

    def test_reserved_direct_process(self):
        self.assertTrue(is_reserved_direct_process("steam"))
        self.assertFalse(is_reserved_direct_process("game"))


if __name__ == "__main__":
    unittest.main()
