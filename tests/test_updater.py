# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from updater import signer_subject_is_allowed, version_tuple


class UpdaterTests(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(version_tuple("v0.22.0"), (0, 22, 0))
        self.assertGreater(version_tuple("0.22.1"), version_tuple("0.22.0"))
        self.assertEqual(version_tuple("1.2-beta"), (1, 2, 0))

    def test_signpath_foundation_subject_is_allowed(self):
        subject = "CN=SignPath Foundation, O=SignPath Foundation, C=AT"
        self.assertTrue(signer_subject_is_allowed(subject, ("SignPath Foundation",)))

    def test_other_valid_publisher_is_rejected(self):
        subject = "CN=Unknown Software LLC, O=Unknown Software LLC, C=US"
        self.assertFalse(signer_subject_is_allowed(subject, ("SignPath Foundation",)))

    def test_empty_expected_subjects_fail_closed(self):
        self.assertFalse(signer_subject_is_allowed("CN=SignPath Foundation", ()))


if __name__ == "__main__":
    unittest.main()
