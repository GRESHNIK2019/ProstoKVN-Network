# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from process_manager import PROCESS_MANAGER, ProcessManager


class ProcessManagerTests(unittest.TestCase):
    def test_spawn_and_stop_reaps_child(self):
        self.assertTrue(PROCESS_MANAGER.primary_instance)
        process = PROCESS_MANAGER.spawn(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertIsNone(process.poll())
        PROCESS_MANAGER.stop(process)
        self.assertIsNotNone(process.poll())

    @unittest.skipUnless(os.name == "nt", "Windows named mutex")
    def test_second_manager_is_not_primary_after_primary_claim(self):
        # Mutex намеренно ленивый: сначала реальная копия приложения должна
        # подтвердить primary, и только после этого вторая копия обязана получить False.
        self.assertTrue(PROCESS_MANAGER.ensure_primary_instance())
        second = ProcessManager()
        try:
            self.assertFalse(second.ensure_primary_instance())
        finally:
            second.close()

    def test_cleanup_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            count = ProcessManager.cleanup_owned_processes(Path(directory))
        self.assertGreaterEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
