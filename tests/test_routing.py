# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import Node
from routing import build_route_rules, make_tun_config


class RoutingTests(unittest.TestCase):
    def make_node(self) -> Node:
        return Node(
            name="test",
            protocol="trojan",
            server="example.com",
            port=443,
            outbound={
                "type": "trojan",
                "tag": "proxy",
                "server": "example.com",
                "server_port": 443,
                "password": "secret",
            },
        )

    def test_smart_routes_selected_apps_and_services(self):
        rules, _, final = build_route_rules(
            "smart_ru",
            custom_vpn_processes=["MyGame.exe"],
            blocklist_paths=[],
        )
        self.assertEqual(final, "direct")
        self.assertTrue(any(rule.get("process_name") == ["MyGame.exe"] and rule.get("outbound") == "proxy" for rule in rules))
        self.assertTrue(any("Discord.exe" in rule.get("process_name", []) and rule.get("outbound") == "proxy" for rule in rules))
        self.assertTrue(any("Telegram.exe" in rule.get("process_name", []) and rule.get("outbound") == "proxy" for rule in rules))
        self.assertTrue(any("steam.exe" in rule.get("process_name", []) and rule.get("outbound") == "direct" for rule in rules))
        self.assertTrue(any(".ru" in rule.get("domain_suffix", []) and rule.get("outbound") == "direct" for rule in rules))

    def test_apps_mode_does_not_force_telegram(self):
        rules, _, final = build_route_rules("game_only", custom_vpn_processes=["client.exe"])
        self.assertEqual(final, "direct")
        self.assertFalse(any("Telegram.exe" in rule.get("process_name", []) for rule in rules))

    def test_global_uses_proxy_as_final_route(self):
        _, _, final = build_route_rules("global")
        self.assertEqual(final, "proxy")

    def test_tun_config_keeps_ru_direct(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_tun_config(
                self.make_node(),
                Path(directory) / "tun.log",
                route_mode="global",
            )
        self.assertEqual(config["route"]["final"], "proxy")
        self.assertTrue(any(".xn--p1ai" in rule.get("domain_suffix", []) for rule in config["route"]["rules"]))

    def test_smart_blocklist_precedes_ru_direct(self):
        with tempfile.TemporaryDirectory() as directory:
            ruleset = Path(directory) / "blocked.srs"
            ruleset.write_bytes(b"test")
            rules, definitions, _ = build_route_rules(
                "smart_ru",
                blocked_ru_vpn=True,
                blocklist_paths=[ruleset],
            )

        self.assertEqual(len(definitions), 1)
        block_index = next(index for index, rule in enumerate(rules) if rule.get("rule_set"))
        ru_index = next(index for index, rule in enumerate(rules) if ".ru" in rule.get("domain_suffix", []))
        self.assertLess(block_index, ru_index)

    def test_user_rule_precedes_builtin_steam_rule(self):
        rules, _, _ = build_route_rules(
            "smart_ru",
            custom_route_rules=[{"type": "process", "value": "steam.exe", "action": "proxy"}],
        )
        user_index = next(
            index for index, rule in enumerate(rules)
            if rule.get("process_name") == ["steam.exe"] and rule.get("outbound") == "proxy"
        )
        builtin_index = next(
            index for index, rule in enumerate(rules)
            if "steam.exe" in rule.get("process_name", []) and rule.get("outbound") == "direct"
        )
        self.assertLess(user_index, builtin_index)

    def test_tun_config_does_not_expose_unused_clash_api(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_tun_config(
                self.make_node(),
                Path(directory) / "tun.log",
                route_mode="smart_ru",
            )
        self.assertNotIn("experimental", config)


if __name__ == "__main__":
    unittest.main()
