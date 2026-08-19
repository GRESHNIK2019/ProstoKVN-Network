# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
import os
from tkinter import ttk

from app_config import PALETTES, THEME_LABELS, detect_windows_theme
from ui.dashboard import build_dashboard
from ui.runtime_safety import install_runtime_safety
from ui.settings_window import SettingsMixin
from ui.tray import TrayController


class ThemeMixin(SettingsMixin):
    def _resolved_theme(self) -> str:
        mode = self.theme_mode_var.get()
        if mode == "system":
            return detect_windows_theme()
        return mode if mode in PALETTES else "dark"

    def _style(self) -> None:
        palette = self.palette
        self.configure(bg=palette["root"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=palette["root"])
        style.configure("Card.TFrame", background=palette["card"])
        style.configure(
            "TButton",
            font=("Segoe UI", 10),
            padding=(10, 7),
            background=palette["card2"],
            foreground=palette["text"],
            bordercolor=palette["border"],
        )
        style.map(
            "TButton",
            background=[("active", palette["segment_hover"])],
            foreground=[("disabled", palette["muted"])],
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(10, 7),
            background=palette["accent"],
            foreground=palette["accent_text"],
            bordercolor=palette["accent"],
        )
        style.map(
            "Primary.TButton",
            background=[("active", palette["accent_hover"]), ("disabled", palette["border"])],
            foreground=[("disabled", palette["muted"])],
        )
        style.configure(
            "Treeview",
            background=palette["card"],
            fieldbackground=palette["card"],
            foreground=palette["text"],
            rowheight=35,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background=palette.get("table_head", palette["card2"]),
            foreground=palette["secondary"],
            relief="flat",
            borderwidth=0,
            padding=(8, 8),
            font=("Segoe UI Semibold", 8),
        )
        style.map(
            "Treeview",
            background=[("selected", palette.get("selected_row", palette["selection"]))],
            foreground=[("selected", palette["text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=palette["card2"],
            troughcolor=palette["card"],
            bordercolor=palette["border"],
            arrowcolor=palette["secondary"],
            relief="flat",
            borderwidth=0,
        )
        style.configure(
            "TCombobox",
            fieldbackground=palette["card2"],
            background=palette["card2"],
            foreground=palette["text"],
            arrowcolor=palette["secondary"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette["card2"])],
            foreground=[("readonly", palette["text"])],
            selectbackground=[("readonly", palette["card2"])],
            selectforeground=[("readonly", palette["text"])],
        )

        # App._build() всё ещё создаёт совместимый старый layout. На idle он
        # заменяется новым dashboard без изменения бизнес-логики и обработчиков.
        self._modern_dashboard_built = False

        # X теперь означает «скрыть в трей». Само окно скрывается только после
        # подтверждённого создания tray icon; при ошибке остаётся доступный выход.
        if not hasattr(self, "_tray_controller"):
            self._tray_controller = TrayController(self)
        self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        self.after_idle(self._wire_settings_ui)

    def _minimize_to_tray(self) -> None:
        controller = getattr(self, "_tray_controller", None)
        if controller is None:
            controller = TrayController(self)
            self._tray_controller = controller

        hidden = controller.minimize()
        if hidden:
            try:
                self.status_var.set("Приложение работает в системном трее")
                append_log = getattr(self, "_append_log", None)
                if callable(append_log):
                    append_log("[APP] Окно скрыто в системный трей")
            except Exception:
                pass

    def _sync_titlebar_theme(self) -> None:
        if os.name != "nt":
            return
        try:
            hwnd = self.winfo_id()
            dark = ctypes.c_int(1 if self.current_theme == "dark" else 0)
            dwm = ctypes.windll.dwmapi
            if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)) != 0:
                dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark))
        except Exception:
            pass

    def _set_theme_mode(self, mode: str) -> None:
        if mode not in THEME_LABELS:
            return
        self.theme_mode_var.set(mode)
        self._save_settings()
        resolved = self._resolved_theme()
        if resolved != self.current_theme:
            self.current_theme = resolved
            self.palette = PALETTES[resolved]
            self._rebuild_ui()
        else:
            self._refresh_theme_buttons()
            self._sync_titlebar_theme()

    def _refresh_theme_buttons(self) -> None:
        if not hasattr(self, "theme_buttons"):
            return
        palette = self.palette
        mode = self.theme_mode_var.get()
        for key, button in list(self.theme_buttons.items()):
            try:
                if not button.winfo_exists():
                    continue
                if key == mode:
                    button.configure(
                        bg=palette["accent"],
                        fg=palette["accent_text"],
                        activebackground=palette["accent_hover"],
                        activeforeground=palette["accent_text"],
                    )
                else:
                    button.configure(
                        bg=palette["segment"],
                        fg=palette["text"],
                        activebackground=palette["segment_hover"],
                        activeforeground=palette["text"],
                    )
            except Exception:
                pass

    def _poll_system_theme(self) -> None:
        if self.theme_mode_var.get() == "system":
            resolved = detect_windows_theme()
            if resolved != self.current_theme:
                self.current_theme = resolved
                self.palette = PALETTES[resolved]
                self._rebuild_ui()
        self.after(1500, self._poll_system_theme)

    def _wire_settings_ui(self) -> None:
        install_runtime_safety(self)
        build_dashboard(self)
