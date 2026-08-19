# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import parse_share_link


class NodeParserTests(unittest.TestCase):
    def test_vless_xhttp_reality(self):
        link = (
            "vless://11111111-1111-1111-1111-111111111111@example.com:443"
            "?type=xhttp&security=reality&sni=example.com&pbk=testkey&sid=01#Node"
        )
        node = parse_share_link(link)
        self.assertEqual(node.protocol, "vless")
        self.assertEqual(node.server, "example.com")
        self.assertEqual(node.extra.get("transport"), "xhttp")
        self.assertEqual(node.extra.get("security"), "reality")
        self.assertEqual(node.engine_label(), "xray")

    def test_trojan(self):
        node = parse_share_link("trojan://secret@example.org:443?security=tls&type=ws&path=%2Fws#Trojan")
        self.assertEqual(node.protocol, "trojan")
        self.assertEqual(node.port, 443)
        self.assertEqual(node.extra.get("transport"), "ws")

    def test_vmess(self):
        payload = {
            "v": "2",
            "ps": "VMess",
            "add": "vmess.example",
            "port": "443",
            "id": "11111111-1111-1111-1111-111111111111",
            "aid": "0",
            "net": "ws",
            "host": "vmess.example",
            "path": "/socket",
            "tls": "tls",
        }
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        node = parse_share_link("vmess://" + encoded)
        self.assertEqual(node.protocol, "vmess")
        self.assertEqual(node.server, "vmess.example")
        self.assertEqual(node.outbound["server_port"], 443)

    def test_shadowsocks(self):
        credentials = base64.urlsafe_b64encode(b"aes-256-gcm:password").decode("ascii").rstrip("=")
        node = parse_share_link(f"ss://{credentials}@127.0.0.1:8388#SS")
        self.assertEqual(node.protocol, "shadowsocks")
        self.assertEqual(node.port, 8388)


if __name__ == "__main__":
    unittest.main()
