# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import vpn_runner


class _FakeSocket:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.bound = None
        self.closed = False

    def bind(self, address):
        if self.fail:
            raise OSError("address not available")
        self.bound = address

    def close(self):
        self.closed = True


class TunLocalIpDetectionTests(unittest.TestCase):
    def test_local_ipv4_assigned_when_udp_bind_succeeds(self):
        fake = _FakeSocket()
        with mock.patch.object(vpn_runner.socket, "socket", return_value=fake):
            self.assertTrue(vpn_runner._local_ipv4_assigned("172.29.77.1"))
        self.assertEqual(fake.bound, ("172.29.77.1", 0))
        self.assertTrue(fake.closed)

    def test_local_ipv4_not_assigned_when_udp_bind_fails(self):
        fake = _FakeSocket(fail=True)
        with mock.patch.object(vpn_runner.socket, "socket", return_value=fake):
            self.assertFalse(vpn_runner._local_ipv4_assigned("172.29.77.1"))
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
