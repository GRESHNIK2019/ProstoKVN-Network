# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cores


class CoreVersionTests(unittest.TestCase):
    def test_parses_singbox_version(self):
        self.assertEqual(cores._extract_version_text("sing-box version 1.13.14\nEnvironment", "sing-box"), "1.13.14")

    def test_parses_xray_version(self):
        self.assertEqual(cores._extract_version_text("Xray 26.7.28 (Xray, Penetrates Everything.)", "xray"), "26.7.28")

    def test_versioned_targets_are_distinct(self):
        original = cores.MANAGED_CORE_DIR
        with tempfile.TemporaryDirectory() as directory:
            cores.MANAGED_CORE_DIR = Path(directory)
            try:
                a = cores._core_target("xray", "26.7.28")
                b = cores._core_target("xray", "26.3.27")
                self.assertNotEqual(a, b)
                self.assertEqual(a.name, "xray-26.7.28")
            finally:
                cores.MANAGED_CORE_DIR = original

    def test_side_by_side_install_does_not_replace_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "xray-26.7.28"
            source.mkdir()
            target.mkdir()
            (source / "xray.exe").write_bytes(b"new")
            (target / "xray.exe").write_bytes(b"existing")
            cores._install_directory_side_by_side(source, target)
            self.assertEqual((target / "xray.exe").read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
