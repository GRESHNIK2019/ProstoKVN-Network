# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from process_manager import ProcessManager


class ProcessManagerTests(unittest.TestCase):
    def test_spawn_and_stop_reaps_child(self):
        manager = ProcessManager()
        try:
            process = manager.spawn(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertIsNone(process.poll())
            manager.stop(process)
            self.assertIsNotNone(process.poll())
        finally:
            manager.close()

    def test_cleanup_non_windows_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            count = ProcessManager.cleanup_owned_processes(Path(directory))
        self.assertGreaterEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
