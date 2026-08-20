# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui.tray import TrayController


class FakeApp:
    def __init__(self) -> None:
        self.withdrawn = False
        self.restored = False
        self.closed = False
        self.destroyed = False
        self.scheduled = []

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))
        return "after-id"

    def withdraw(self) -> None:
        self.withdrawn = True

    def deiconify(self) -> None:
        self.restored = True

    def state(self, value: str) -> None:
        if value == "normal":
            self.restored = True

    def lift(self) -> None:
        pass

    def focus_force(self) -> None:
        pass

    def on_close(self) -> None:
        self.closed = True

    def destroy(self) -> None:
        self.destroyed = True


class TrayControllerTests(unittest.TestCase):
    def test_minimize_hides_only_when_tray_started(self):
        app = FakeApp()
        tray = TrayController(app)
        tray.start = lambda: True
        self.assertTrue(tray.minimize())
        self.assertTrue(app.withdrawn)
        self.assertFalse(app.closed)

    def test_show_command_restores_window(self):
        app = FakeApp()
        tray = TrayController(app)
        tray._request_show()
        tray._drain_commands()
        self.assertTrue(app.restored)

    def test_exit_command_closes_application(self):
        app = FakeApp()
        tray = TrayController(app)
        tray._request_exit()
        tray._drain_commands()
        self.assertTrue(app.closed)

    def test_fallback_icon_does_not_need_external_ico(self):
        image = TrayController._fallback_icon_image()
        self.assertEqual(image.size, (64, 64))

    def test_theme_wires_x_to_tray(self):
        source = (ROOT / "src" / "ui" / "theme.py").read_text(encoding="utf-8")
        self.assertIn('self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)', source)
        self.assertIn("TrayController(self)", source)

    def test_build_embeds_tray_backend_and_uac_manifest(self):
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn('--uac-admin', workflow)
        self.assertIn('--add-data "src/assets/ProstoKVNNetwork.ico;assets"', workflow)
        self.assertIn('--hidden-import "pystray._win32"', workflow)


if __name__ == "__main__":
    unittest.main()
