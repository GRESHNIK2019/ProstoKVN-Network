# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from updater import version_tuple


class UpdaterTests(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(version_tuple("v0.22.0"), (0, 22, 0))
        self.assertGreater(version_tuple("0.22.1"), version_tuple("0.22.0"))
        self.assertEqual(version_tuple("1.2-beta"), (1, 2, 0))


if __name__ == "__main__":
    unittest.main()
