# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
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

    def poll(self):
        return None if self.running else 1


class VpnRunnerLifecycleTests(unittest.TestCase):
    def make_node(self, protocol: str = "vless") -> Node:
        return Node(
            name="test",
            protocol=protocol,
            server="127.0.0.1",
            port=443,
            outbound={"type": protocol, "tag": "proxy"},
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

    def test_failed_start_cleans_started_xray(self):
        runner = self.make_runner()
        fake_xray = FakeProcess(True)

        def fail_bridge():
            runner.xray_proc = fake_xray
            raise RuntimeError("bridge failed")

        stopped = []
        with (
            mock.patch.object(runner, "_start_xray_bridge", side_effect=fail_bridge),
            mock.patch.object(runner, "_prepare_runtime_files"),
            mock.patch.object(vpn_runner, "_kill_stale_runtime_processes"),
            mock.patch.object(vpn_runner, "_stop_process_tree", side_effect=lambda proc: stopped.append(proc)),
        ):
            with self.assertRaisesRegex(RuntimeError, "bridge failed"):
                runner.start()

        self.assertIn(fake_xray, stopped)
        self.assertIsNone(runner.proc)
        self.assertIsNone(runner.xray_proc)
        self.assertFalse(runner._starting)


if __name__ == "__main__":
    unittest.main()
