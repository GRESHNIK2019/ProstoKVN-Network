# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import external_process


class ExternalProcessTests(unittest.TestCase):
    def test_sanitized_environment_removes_mei_from_path(self):
        with tempfile.TemporaryDirectory() as directory:
            mei = Path(directory) / "_MEI123456"
            other = Path(directory) / "bin"
            mei.mkdir()
            other.mkdir()
            env = {"PATH": os.pathsep.join((str(mei), str(other)))}
            with mock.patch.object(external_process.sys, "_MEIPASS", str(mei), create=True):
                clean = external_process.sanitized_environment(env)
            self.assertNotIn(str(mei), clean["PATH"])
            self.assertIn(str(other), clean["PATH"])

    def test_run_external_returns_completed_process(self):
        result = external_process.run_external(
            [sys.executable, "-c", "print('ok')"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual((result.stdout or "").strip(), "ok")

    def test_timeout_reaps_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            external_process.run_external(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                capture_output=True,
                text=True,
                timeout=0.1,
            )


if __name__ == "__main__":
    unittest.main()
