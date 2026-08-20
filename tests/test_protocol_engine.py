# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import Node, parse_vless, parse_hy2, parse_tuic, parse_ss, parse_trojan
from protocol_engine import choose_engine, fatal_issues, make_xray_vless_outbound, validate_node


VLESS_UUID = "11111111-1111-1111-1111-111111111111"


class ProtocolEngineTests(unittest.TestCase):
    def test_vless_xhttp_reality_requires_xray_and_preserves_public_key(self):
        node = parse_vless(
            f"vless://{VLESS_UUID}@example.com:443?type=xhttp&security=reality"
            "&sni=cdn.example.com&pbk=PUBKEY&sid=abcd&path=%2Fapi&mode=auto#xhttp"
        )
        self.assertEqual(fatal_issues(node), [])
        plan = choose_engine(node, xray_available=True)
        self.assertEqual(plan.engine, "xray")
        self.assertTrue(plan.requires_xray)
        stream = make_xray_vless_outbound(node)["streamSettings"]
        self.assertEqual(stream["network"], "xhttp")
        self.assertEqual(stream["realitySettings"]["publicKey"], "PUBKEY")
        self.assertNotIn("password", stream["realitySettings"])

    def test_vless_ws_tls_uses_compatible_xray_schema(self):
        node = parse_vless(
            f"vless://{VLESS_UUID}@example.com:443?type=ws&security=tls"
            "&sni=example.com&host=edge.example.com&path=%2Fsocket#ws"
        )
        stream = make_xray_vless_outbound(node)["streamSettings"]
        self.assertEqual(stream["network"], "websocket")
        self.assertEqual(stream["wsSettings"]["path"], "/socket")
        self.assertEqual(stream["wsSettings"]["host"], "edge.example.com")
        self.assertNotIn("method", stream)

    def test_vless_grpc_reality(self):
        node = parse_vless(
            f"vless://{VLESS_UUID}@example.com:443?type=grpc&security=reality"
            "&sni=example.com&pbk=PUBKEY&sid=01&serviceName=edge#grpc"
        )
        stream = make_xray_vless_outbound(node)["streamSettings"]
        self.assertEqual(stream["network"], "grpc")
        self.assertEqual(stream["grpcSettings"]["serviceName"], "edge")
        self.assertEqual(stream["realitySettings"]["publicKey"], "PUBKEY")

    def test_vision_rejects_websocket(self):
        node = parse_vless(
            f"vless://{VLESS_UUID}@example.com:443?type=ws&security=tls&flow=xtls-rprx-vision#bad"
        )
        codes = {issue.code for issue in fatal_issues(node)}
        self.assertIn("vless.vision.transport", codes)

    def test_reality_requires_public_key(self):
        node = parse_vless(
            f"vless://{VLESS_UUID}@example.com:443?type=grpc&security=reality&sni=example.com#bad"
        )
        codes = {issue.code for issue in fatal_issues(node)}
        self.assertIn("reality.public_key", codes)

    def test_hysteria2_requires_tls_and_password(self):
        node = parse_hy2("hysteria2://secret@example.com:443?sni=example.com#hy2")
        self.assertEqual(fatal_issues(node), [])
        self.assertEqual(choose_engine(node).engine, "sing-box")

    def test_hysteria2_unknown_obfs_is_rejected_for_pinned_core(self):
        node = parse_hy2("hysteria2://secret@example.com:443?obfs=gecko&obfs-password=x#hy2")
        codes = {issue.code for issue in fatal_issues(node)}
        self.assertIn("hy2.obfs.version", codes)

    def test_tuic_validation(self):
        node = parse_tuic(
            f"tuic://{VLESS_UUID}:secret@example.com:443?congestion_control=bbr&udp_relay_mode=native&sni=example.com#tuic"
        )
        self.assertEqual(fatal_issues(node), [])
        self.assertEqual(choose_engine(node).engine, "sing-box")

    def test_shadowsocks_aead_validation(self):
        # SIP002: base64(method:password) before @.
        node = parse_ss("ss://YWVzLTI1Ni1nY206c2VjcmV0@example.com:8388#ss")
        self.assertEqual(fatal_issues(node), [])
        self.assertEqual(choose_engine(node).engine, "sing-box")

    def test_trojan_without_password_is_invalid(self):
        node = Node(
            name="trojan",
            protocol="trojan",
            server="example.com",
            port=443,
            outbound={"type": "trojan", "password": "", "tls": {"enabled": True}},
            extra={"security": "tls"},
        )
        self.assertTrue(fatal_issues(node))

    def test_public_vless_without_security_is_warning_not_crash(self):
        node = parse_vless(f"vless://{VLESS_UUID}@example.com:80?type=tcp&security=none#plain")
        issues = validate_node(node)
        self.assertFalse(any(issue.level == "error" for issue in issues))
        self.assertTrue(any(issue.code == "vless.public.no_security" for issue in issues))


if __name__ == "__main__":
    unittest.main()
