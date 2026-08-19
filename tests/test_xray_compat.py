# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import Node
import node_tester
from xray_compat import install_xray_config_compat


class XrayCompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_xray_config_compat()

    def make_node(self, transport: str, security: str = "tls") -> Node:
        source = (
            "vless://11111111-1111-1111-1111-111111111111@example.com:443"
            f"?type={transport}&security={security}&sni=example.com"
            "&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=01"
        )
        return Node(
            name="test",
            protocol="vless",
            server="example.com",
            port=443,
            source=source,
            outbound={
                "type": "vless",
                "uuid": "11111111-1111-1111-1111-111111111111",
            },
            extra={"transport": transport, "security": security},
        )

    def test_websocket_uses_network_field(self):
        outbound = node_tester.make_xray_vless_outbound(self.make_node("ws"))
        stream = outbound["streamSettings"]
        self.assertEqual(stream["network"], "websocket")
        self.assertNotIn("method", stream)

    def test_grpc_uses_network_field(self):
        outbound = node_tester.make_xray_vless_outbound(self.make_node("grpc"))
        stream = outbound["streamSettings"]
        self.assertEqual(stream["network"], "grpc")
        self.assertNotIn("method", stream)

    def test_xhttp_reality_uses_network_and_public_key(self):
        outbound = node_tester.make_xray_vless_outbound(self.make_node("xhttp", "reality"))
        stream = outbound["streamSettings"]
        self.assertEqual(stream["network"], "xhttp")
        self.assertNotIn("method", stream)
        self.assertIn("publicKey", stream["realitySettings"])
        self.assertNotIn("password", stream["realitySettings"])


if __name__ == "__main__":
    unittest.main()
