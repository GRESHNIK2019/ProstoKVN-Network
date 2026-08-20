# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import vpn_runner


@unittest.skipUnless(os.name == "nt", "Windows TUN detection")
class TunDetectionTests(unittest.TestCase):
    def test_tun_is_ready_when_ipv4_probe_succeeds_even_if_name_is_not_returned(self):
        result = mock.Mock(returncode=0, stdout="READY\r\n", stderr="")
        with mock.patch.object(vpn_runner, "run_external", return_value=result) as mocked:
            self.assertTrue(
                vpn_runner._interface_probably_exists(
                    "prostokvn_network_tun",
                    "172.29.77.1",
                )
            )
        command = mocked.call_args.args[0]
        self.assertIn("Get-NetIPAddress", command[-1])
        self.assertIn("172.29.77.1", command[-1])

    def test_tun_falls_back_to_netsh_when_powershell_probe_fails(self):
        powershell = mock.Mock(returncode=1, stdout="", stderr="failed")
        netsh = mock.Mock(returncode=0, stdout="IP Address: 172.29.77.1\r\n", stderr="")
        with mock.patch.object(vpn_runner, "run_external", side_effect=[powershell, netsh]):
            self.assertTrue(vpn_runner._interface_probably_exists("prostokvn_network_tun"))


if __name__ == "__main__":
    unittest.main()
