# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodes import Node
import vpn_runner
from vpn_runner import TunRunner


class FakeProcess:
    def __init__(self, running: bool = True):
        self.running = running
        self.pid = 12345

    def poll(self):
        return None if self.running else 1


class VpnRunnerLifecycleTests(unittest.TestCase):
    def make_node(self, protocol: str = "vless") -> Node:
        if protocol == "vless":
            outbound = {
                "type": "vless",
                "uuid": "11111111-1111-1111-1111-111111111111",
            }
            extra = {"transport": "raw", "security": "none"}
        elif protocol == "trojan":
            outbound = {
                "type": "trojan",
                "password": "secret",
                "tls": {"enabled": True, "server_name": "localhost"},
            }
            extra = {"security": "tls"}
        else:
            outbound = {"type": protocol}
            extra = {}
        return Node(
            name="test",
            protocol=protocol,
            server="127.0.0.1",
            port=443,
            outbound=outbound,
            extra=extra,
        )

    def make_runner(self, protocol: str = "vless") -> TunRunner:
        return TunRunner(
            Path("sing-box.exe"),
            self.make_node(protocol),
            xray=Path("xray.exe") if protocol == "vless" else None,
        )

    def test_watchdog_treats_starting_runner_as_running(self):
        runner = self.make_runner()
        runner._starting = True
        self.assertTrue(runner.running())

    def test_vless_runner_requires_both_processes(self):
        runner = self.make_runner()
        runner.proc = FakeProcess(True)
        runner.xray_proc = FakeProcess(False)
        self.assertFalse(runner.running())
        runner.xray_proc = FakeProcess(True)
        self.assertTrue(runner.running())

    def test_non_vless_runner_only_requires_singbox(self):
        runner = self.make_runner("trojan")
        runner.proc = FakeProcess(True)
        self.assertTrue(runner.running())

    def test_health_failure_makes_runner_not_running(self):
        runner = self.make_runner("trojan")
        runner.proc = FakeProcess(True)
        runner._health_failure = "TUN-интерфейс исчез"
        self.assertFalse(runner.running())
        self.assertIn("TUN-интерфейс исчез", runner.failure_reason())

    def test_failed_start_cleans_started_xray(self):
        runner = self.make_runner()
        fake_xray = FakeProcess(True)

        def fail_bridge():
            runner.xray_proc = fake_xray
            raise RuntimeError("bridge failed")

        stopped = []
        with (
            mock.patch.object(runner, "_validate"),
            mock.patch.object(runner, "_start_xray_bridge", side_effect=fail_bridge),
            mock.patch.object(runner, "_prepare_runtime_files"),
            mock.patch.object(vpn_runner.PROCESS_MANAGER, "cleanup_owned_processes", return_value=0),
            mock.patch.object(vpn_runner.PROCESS_MANAGER, "stop", side_effect=lambda proc: stopped.append(proc)),
        ):
            with self.assertRaisesRegex(RuntimeError, "bridge failed"):
                runner.start()

        self.assertIn(fake_xray, stopped)
        self.assertIsNone(runner.proc)
        self.assertIsNone(runner.xray_proc)
        self.assertFalse(runner._starting)

    def test_start_fails_if_tun_interface_never_appears(self):
        runner = self.make_runner("trojan")
        fake_tun = FakeProcess(True)
        check_result = mock.Mock(returncode=0, stderr="", stdout="")
        stopped = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner.cfg_path = root / "active_tun.json"
            runner.log_path = root / "active_tun.log"
            runner.xray_cfg_path = root / "active_xray.json"
            runner.xray_log_path = root / "active_xray.log"

            with (
                mock.patch.object(runner, "_validate"),
                mock.patch.object(vpn_runner.PROCESS_MANAGER, "cleanup_owned_processes", return_value=0),
                mock.patch.object(vpn_runner.PROCESS_MANAGER, "spawn", return_value=fake_tun),
                mock.patch.object(vpn_runner.PROCESS_MANAGER, "stop", side_effect=lambda proc: stopped.append(proc)),
                mock.patch.object(vpn_runner, "run_external", return_value=check_result),
                mock.patch.object(vpn_runner, "_wait_tun_interface", return_value=False),
            ):
                with self.assertRaisesRegex(RuntimeError, "TUN-интерфейс"):
                    runner.start()

        self.assertIn(fake_tun, stopped)
        self.assertIsNone(runner.proc)
        self.assertFalse(runner._starting)

    def test_wait_tun_interface_requires_real_interface(self):
        process = FakeProcess(True)
        with mock.patch.object(vpn_runner, "_interface_probably_exists", return_value=False):
            self.assertFalse(vpn_runner._wait_tun_interface("prostokvn_network_tun", process, timeout=0))


if __name__ == "__main__":
    unittest.main()
