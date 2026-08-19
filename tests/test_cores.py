# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cores


class CoreInstallerTests(unittest.TestCase):
    def test_release_url_is_pinned_to_tag(self):
        self.assertEqual(
            cores._release_api_url("SagerNet/sing-box", "1.13.14"),
            "https://api.github.com/repos/SagerNet/sing-box/releases/tags/v1.13.14",
        )
        self.assertNotIn("/latest", cores._release_api_url("XTLS/Xray-core", "26.7.28"))

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.zip"
            destination = root / "out"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.exe", b"bad")
            with self.assertRaisesRegex(RuntimeError, "Небезопасный путь"):
                cores._safe_extract_zip(archive, destination)
            self.assertFalse((root / "escape.exe").exists())

    def test_safe_zip_extracts_normally(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "ok.zip"
            destination = root / "out"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sing-box/sing-box.exe", b"exe")
            cores._safe_extract_zip(archive, destination)
            self.assertEqual((destination / "sing-box" / "sing-box.exe").read_bytes(), b"exe")

    def test_managed_singbox_is_found_without_saved_explicit_path(self):
        with tempfile.TemporaryDirectory() as directory:
            managed_root = Path(directory)
            exe = managed_root / "sing-box" / "sing-box.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"exe")
            with (
                mock.patch.object(cores, "MANAGED_CORE_DIR", managed_root),
                mock.patch.dict(cores.os.environ, {"SINGBOX_EXE": ""}),
            ):
                self.assertEqual(cores.find_singbox_binary(), exe.resolve())


if __name__ == "__main__":
    unittest.main()
