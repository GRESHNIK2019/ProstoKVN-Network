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


if __name__ == "__main__":
    unittest.main()
