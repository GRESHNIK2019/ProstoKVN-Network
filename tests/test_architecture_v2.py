# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paths import RUNTIME_DIR, USER_DATA_DIR


class ArchitectureV2Tests(unittest.TestCase):
    def test_runtime_is_under_user_data_not_source_bundle(self):
        self.assertEqual(RUNTIME_DIR.parent, USER_DATA_DIR)
        self.assertEqual(RUNTIME_DIR.name, "runtime")

    def test_runtime_safety_tracks_starting_runner(self):
        source = (ROOT / "src" / "ui" / "runtime_safety.py").read_text(encoding="utf-8")
        self.assertIn("_starting_runner", source)
        self.assertIn("self._starting_runner = runner", source)

    def test_node_tester_uses_process_manager(self):
        source = (ROOT / "src" / "node_tester.py").read_text(encoding="utf-8")
        self.assertIn("PROCESS_MANAGER.spawn", source)
        self.assertIn("PROCESS_MANAGER.stop(process)", source)

    def test_xray_builder_has_no_runtime_monkey_patch_dependency(self):
        settings_source = (ROOT / "src" / "settings_store.py").read_text(encoding="utf-8")
        self.assertNotIn("install_xray_config_compat", settings_source)

    def test_core_installer_does_not_use_old_directory_swap(self):
        source = (ROOT / "src" / "cores.py").read_text(encoding="utf-8")
        self.assertNotIn("target.with_name(target.name + \".old\")", source)
        self.assertIn("_install_directory_side_by_side", source)


if __name__ == "__main__":
    unittest.main()
