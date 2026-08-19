# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import Node
from node_tester import make_xray_vless_outbound


class XrayVlessTests(unittest.TestCase):
    def make_share_node(self, transport: str, security: str = "tls") -> Node:
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

    def test_websocket_uses_current_method_field(self):
        outbound = make_xray_vless_outbound(self.make_share_node("ws"))
        stream = outbound["streamSettings"]
        self.assertEqual(stream["method"], "websocket")
        self.assertNotIn("network", stream)

    def test_grpc_uses_current_method_field(self):
        outbound = make_xray_vless_outbound(self.make_share_node("grpc"))
        stream = outbound["streamSettings"]
        self.assertEqual(stream["method"], "grpc")
        self.assertNotIn("network", stream)

    def test_xhttp_reality_uses_password_public_key_field(self):
        outbound = make_xray_vless_outbound(self.make_share_node("xhttp", "reality"))
        stream = outbound["streamSettings"]
        self.assertEqual(stream["method"], "xhttp")
        self.assertIn("password", stream["realitySettings"])
        self.assertNotIn("publicKey", stream["realitySettings"])

    def test_clash_nested_grpc_reality_is_preserved(self):
        node = Node(
            name="clash",
            protocol="vless",
            server="example.com",
            port=443,
            source="clash",
            outbound={
                "type": "vless",
                "uuid": "11111111-1111-1111-1111-111111111111",
            },
            extra={
                "transport": "grpc",
                "security": "reality",
                "clash": {
                    "type": "vless",
                    "network": "grpc",
                    "tls": True,
                    "servername": "cdn.example.com",
                    "client-fingerprint": "chrome",
                    "grpc-opts": {"grpc-service-name": "edge-service"},
                    "reality-opts": {
                        "public-key": "PUBKEY",
                        "short-id": "abcd",
                    },
                },
            },
        )
        outbound = make_xray_vless_outbound(node)
        stream = outbound["streamSettings"]
        self.assertEqual(stream["method"], "grpc")
        self.assertEqual(stream["grpcSettings"]["serviceName"], "edge-service")
        self.assertEqual(stream["realitySettings"]["serverName"], "cdn.example.com")
        self.assertEqual(stream["realitySettings"]["password"], "PUBKEY")
        self.assertEqual(stream["realitySettings"]["shortId"], "abcd")

    def test_singbox_json_transport_and_tls_are_preserved(self):
        node = Node(
            name="json",
            protocol="vless",
            server="json.example.com",
            port=443,
            source="sing-box-json",
            outbound={
                "type": "vless",
                "uuid": "11111111-1111-1111-1111-111111111111",
                "transport": {
                    "type": "ws",
                    "path": "/socket",
                    "headers": {"Host": "edge.example.com", "X-Test": "1"},
                },
                "tls": {
                    "enabled": True,
                    "server_name": "edge.example.com",
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                },
            },
            extra={"transport": "ws", "security": "tls"},
        )
        outbound = make_xray_vless_outbound(node)
        stream = outbound["streamSettings"]
        self.assertEqual(stream["method"], "websocket")
        self.assertEqual(stream["wsSettings"]["path"], "/socket")
        self.assertEqual(stream["wsSettings"]["host"], "edge.example.com")
        self.assertEqual(stream["wsSettings"]["headers"]["X-Test"], "1")
        self.assertEqual(stream["tlsSettings"]["serverName"], "edge.example.com")
        self.assertEqual(stream["tlsSettings"]["fingerprint"], "chrome")


if __name__ == "__main__":
    unittest.main()
