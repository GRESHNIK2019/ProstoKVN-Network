# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_config import PALETTES, STRATEGIES, STRATEGY_DESCRIPTIONS, THEME_LABELS, detect_windows_theme
from paths import SETTINGS_PATH
from routing import normalize_process_names, normalize_route_rules
from settings_store import load_settings, save_settings


_RULE_TYPE_LABELS = {
    "process": "Приложение",
    "domain_suffix": "Домен",
    "ip_cidr": "IP / подсеть",
}
_RULE_TYPE_KEYS = {value: key for key, value in _RULE_TYPE_LABELS.items()}
_RULE_ACTION_LABELS = {
    "proxy": "VPN",
    "direct": "DIRECT",
    "block": "BLOCK",
}
_RULE_ACTION_KEYS = {value: key for key, value in _RULE_ACTION_LABELS.items()}


class ThemeMixin:
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
            rowheight=28,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=palette["card2"],
            foreground=palette["text"],
            relief="flat",
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Treeview",
            background=[("selected", palette["selection"])],
            foreground=[("selected", palette["text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=palette["card2"],
            troughcolor=palette["card"],
            bordercolor=palette["border"],
            arrowcolor=palette["text"],
        )

        # Главное окно строится сразу после _style(). На idle уже можно убрать
        # старые элементы маршрутизации и привязать пункт «Настройки».
        self.after_idle(self._wire_settings_ui)

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
        for key, button in self.theme_buttons.items():
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

    def _poll_system_theme(self) -> None:
        if self.theme_mode_var.get() == "system":
            resolved = detect_windows_theme()
            if resolved != self.current_theme:
                self.current_theme = resolved
                self.palette = PALETTES[resolved]
                self._rebuild_ui()
        self.after(1500, self._poll_system_theme)

    # ---------------- Новое окно настроек ----------------
    def _walk_widgets(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self._walk_widgets(child)

    def _wire_settings_ui(self) -> None:
        if not self.winfo_exists():
            return

        # Убираем маршрутизацию/тему с экрана серверов: этот экран теперь только
        # про подписку, узлы и запуск VPN.
        try:
            self.apply_btn.pack_forget()
        except Exception:
            pass
        try:
            if self.strategy_buttons:
                next(iter(self.strategy_buttons.values())).master.pack_forget()
        except Exception:
            pass
        try:
            if self.theme_buttons:
                next(iter(self.theme_buttons.values())).master.pack_forget()
        except Exception:
            pass
        try:
            self.advanced.pack_forget()
            self.advanced_open = False
        except Exception:
            pass

        for widget in list(self._walk_widgets(self)):
            try:
                text = str(widget.cget("text"))
            except Exception:
                continue
            if text == "Настройки":
                try:
                    widget.configure(cursor="hand2")
                    widget.bind("<Button-1>", lambda _event: self.open_settings("routing"))
                except Exception:
                    pass
            elif text in {"Расширенные", "Steam.exe DIRECT"}:
                try:
                    widget.pack_forget()
                except Exception:
                    pass

    def open_settings(self, page: str = "routing") -> None:
        current = getattr(self, "settings_window", None)
        if current is not None:
            try:
                if current.winfo_exists():
                    current.lift()
                    current.focus_force()
                    switch = getattr(self, "_settings_switch", None)
                    if switch:
                        switch(page)
                    return
            except Exception:
                pass

        self._migrate_legacy_app_rules()
        p = self.palette
        window = tk.Toplevel(self)
        self.settings_window = window
        window.title("Настройки — ProstoKVN Network")
        window.geometry("960x650")
        window.minsize(820, 560)
        window.configure(bg=p["root"])
        window.transient(self)

        body = tk.Frame(window, bg=p["root"])
        body.pack(fill="both", expand=True, padx=14, pady=14)

        sidebar = tk.Frame(body, bg=p["card"], width=190, highlightbackground=p["border"], highlightthickness=1)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="Настройки", bg=p["card"], fg=p["text"], font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=14, pady=(14, 12))

        content = tk.Frame(body, bg=p["card"], highlightbackground=p["border"], highlightthickness=1)
        content.pack(side="left", fill="both", expand=True)

        pages = {
            "general": self._build_general_settings(content),
            "routing": self._build_routing_settings(content),
            "cores": self._build_core_settings(content),
        }
        nav_buttons: dict[str, tk.Button] = {}

        def switch(name: str):
            if name not in pages:
                name = "routing"
            for frame in pages.values():
                frame.pack_forget()
            pages[name].pack(fill="both", expand=True)
            for key, button in nav_buttons.items():
                if key == name:
                    button.configure(bg=p["accent"], fg=p["accent_text"])
                else:
                    button.configure(bg=p["card"], fg=p["text"])

        for key, label in (("general", "Основные"), ("routing", "Маршрутизация"), ("cores", "Ядра")):
            button = tk.Button(
                sidebar, text=label, anchor="w", command=lambda k=key: switch(k),
                bg=p["card"], fg=p["text"], activebackground=p["segment_hover"],
                activeforeground=p["text"], relief="flat", bd=0, padx=14, pady=10,
                font=("Segoe UI", 10),
            )
            button.pack(fill="x", padx=6, pady=2)
            nav_buttons[key] = button

        self._settings_switch = switch
        switch(page)

    def _settings_page(self, parent, title: str, description: str):
        p = self.palette
        frame = tk.Frame(parent, bg=p["card"])
        tk.Label(frame, text=title, bg=p["card"], fg=p["text"], font=("Segoe UI Semibold", 15)).pack(anchor="w", padx=18, pady=(18, 3))
        tk.Label(frame, text=description, bg=p["card"], fg=p["secondary"], font=("Segoe UI", 9), justify="left", wraplength=680).pack(anchor="w", padx=18, pady=(0, 14))
        return frame

    def _build_general_settings(self, parent):
        p = self.palette
        frame = self._settings_page(parent, "Основные", "Внешний вид и поведение приложения.")

        section = tk.Frame(frame, bg=p["card2"], highlightbackground=p["border"], highlightthickness=1)
        section.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(section, text="Тема", bg=p["card2"], fg=p["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=12, pady=(12, 8))
        row = tk.Frame(section, bg=p["card2"])
        row.pack(anchor="w", padx=12, pady=(0, 12))
        for key in ("system", "light", "dark"):
            tk.Button(
                row, text=THEME_LABELS[key], command=lambda k=key: self._set_theme_mode(k),
                bg=p["segment"], fg=p["text"], activebackground=p["segment_hover"],
                activeforeground=p["text"], relief="flat", bd=0, padx=12, pady=6,
            ).pack(side="left", padx=(0, 6))

        auto = tk.Checkbutton(
            frame, text="Автопереподключение VPN при неожиданной остановке",
            variable=self.auto_reconnect_var, command=self._save_settings,
            bg=p["card"], fg=p["text"], activebackground=p["card"],
            activeforeground=p["text"], selectcolor=p["card2"], bd=0,
        )
        auto.pack(anchor="w", padx=18, pady=8)
        return frame

    def _load_route_rules(self) -> list[dict[str, str]]:
        data = load_settings(SETTINGS_PATH)
        return normalize_route_rules(data.get("route_rules") or [])

    def _persist_route_rules(self) -> None:
        data = load_settings(SETTINGS_PATH)
        data["route_rules"] = normalize_route_rules(getattr(self, "route_rules", []))
        save_settings(SETTINGS_PATH, data)

    def _migrate_legacy_app_rules(self) -> None:
        legacy = normalize_process_names(getattr(self, "custom_vpn_processes", []))
        if not legacy:
            return
        rules = self._load_route_rules()
        existing = {(r["type"], r["value"].lower()) for r in rules}
        changed = False
        for name in legacy:
            key = ("process", name.lower())
            if key not in existing:
                rules.append({"type": "process", "value": name, "action": "proxy"})
                existing.add(key)
                changed = True
        if changed:
            self.route_rules = normalize_route_rules(rules)
            self._persist_route_rules()
        self.custom_vpn_processes = []
        self._save_settings()
        try:
            self._refresh_custom_apps_label()
        except Exception:
            pass

    def _build_routing_settings(self, parent):
        p = self.palette
        frame = self._settings_page(
            parent,
            "Маршрутизация",
            "Здесь задаётся, какой трафик идёт через VPN, напрямую или блокируется. Первое совпавшее правило имеет приоритет.",
        )

        mode_box = tk.Frame(frame, bg=p["card2"], highlightbackground=p["border"], highlightthickness=1)
        mode_box.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(mode_box, text="Режим маршрутизации", bg=p["card2"], fg=p["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=12, pady=(12, 7))
        modes = tk.Frame(mode_box, bg=p["card2"])
        modes.pack(anchor="w", padx=12, pady=(0, 5))
        mode_buttons = {}

        def select_mode(key: str):
            self._set_strategy(key)
            for item_key, button in mode_buttons.items():
                selected = item_key == self.strategy_key_var.get()
                button.configure(
                    bg=p["accent"] if selected else p["segment"],
                    fg=p["accent_text"] if selected else p["text"],
                )
            desc.configure(text=STRATEGY_DESCRIPTIONS.get(key, ""))

        for key in ("smart_ru", "game_only", "global"):
            button = tk.Button(
                modes, text=STRATEGIES[key], command=lambda k=key: select_mode(k),
                bg=p["segment"], fg=p["text"], activebackground=p["segment_hover"],
                activeforeground=p["text"], relief="flat", bd=0, padx=14, pady=6,
            )
            button.pack(side="left", padx=(0, 6))
            mode_buttons[key] = button
        desc = tk.Label(mode_box, bg=p["card2"], fg=p["secondary"], font=("Segoe UI", 9), anchor="w")
        desc.pack(fill="x", padx=12, pady=(2, 12))
        select_mode(self.strategy_key_var.get())

        rules_box = tk.Frame(frame, bg=p["card2"], highlightbackground=p["border"], highlightthickness=1)
        rules_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        head = tk.Frame(rules_box, bg=p["card2"])
        head.pack(fill="x", padx=10, pady=(10, 8))
        tk.Label(head, text="Пользовательские правила", bg=p["card2"], fg=p["text"], font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(head, text="DIRECT / VPN / BLOCK", bg=p["card2"], fg=p["muted"], font=("Segoe UI", 8)).pack(side="right")

        table_wrap = tk.Frame(rules_box, bg=p["card2"])
        table_wrap.pack(fill="both", expand=True, padx=10)
        tree = ttk.Treeview(table_wrap, columns=("type", "value", "action"), show="headings", selectmode="browse")
        tree.heading("type", text="Тип")
        tree.heading("value", text="Значение")
        tree.heading("action", text="Маршрут")
        tree.column("type", width=120, stretch=False)
        tree.column("value", width=380, stretch=True)
        tree.column("action", width=100, stretch=False, anchor="center")
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.route_tree = tree
        self.route_rules = self._load_route_rules()
        self._refresh_route_tree()
        tree.bind("<Double-Button-1>", lambda _event: self._edit_route_rule())

        buttons = tk.Frame(rules_box, bg=p["card2"])
        buttons.pack(fill="x", padx=10, pady=10)
        tk.Button(
            buttons, text="+ Добавить правило", command=self._add_route_rule,
            bg=p["accent"], fg=p["accent_text"], activebackground=p["accent_hover"],
            activeforeground=p["accent_text"], relief="flat", bd=0, padx=12, pady=6,
        ).pack(side="left")
        tk.Button(
            buttons, text="Изменить", command=self._edit_route_rule,
            bg=p["segment"], fg=p["text"], activebackground=p["segment_hover"],
            activeforeground=p["text"], relief="flat", bd=0, padx=12, pady=6,
        ).pack(side="left", padx=(7, 0))
        tk.Button(
            buttons, text="Удалить", command=self._remove_route_rule,
            bg=p["segment"], fg=p["bad"], activebackground=p["segment_hover"],
            activeforeground=p["bad"], relief="flat", bd=0, padx=12, pady=6,
        ).pack(side="left", padx=(7, 0))

        footer = tk.Frame(frame, bg=p["card"])
        footer.pack(fill="x", padx=18, pady=(0, 16))
        self.routing_apply_hint = tk.Label(footer, text="Изменения правил сохраняются автоматически.", bg=p["card"], fg=p["secondary"], font=("Segoe UI", 9))
        self.routing_apply_hint.pack(side="left")
        tk.Button(
            footer, text="Применить к VPN", command=self._apply_routing_now,
            bg=p["accent"], fg=p["accent_text"], activebackground=p["accent_hover"],
            activeforeground=p["accent_text"], relief="flat", bd=0, padx=14, pady=7,
        ).pack(side="right")
        return frame

    def _refresh_route_tree(self) -> None:
        tree = getattr(self, "route_tree", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            return
        for index, rule in enumerate(normalize_route_rules(getattr(self, "route_rules", []))):
            tree.insert(
                "", "end", iid=str(index),
                values=(
                    _RULE_TYPE_LABELS.get(rule["type"], rule["type"]),
                    rule["value"],
                    _RULE_ACTION_LABELS.get(rule["action"], rule["action"]),
                ),
            )

    def _selected_route_index(self) -> int | None:
        tree = getattr(self, "route_tree", None)
        if tree is None:
            return None
        selection = tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except Exception:
            return None

    def _add_route_rule(self) -> None:
        self._route_rule_editor(None)

    def _edit_route_rule(self) -> None:
        index = self._selected_route_index()
        if index is None or index < 0 or index >= len(self.route_rules):
            return
        self._route_rule_editor(index)

    def _remove_route_rule(self) -> None:
        index = self._selected_route_index()
        if index is None or index < 0 or index >= len(self.route_rules):
            return
        del self.route_rules[index]
        self.route_rules = normalize_route_rules(self.route_rules)
        self._persist_route_rules()
        self._refresh_route_tree()
        try:
            self._append_log("[ROUTE] Пользовательское правило удалено")
        except Exception:
            pass

    def _route_rule_editor(self, index: int | None) -> None:
        p = self.palette
        parent = getattr(self, "settings_window", self)
        dialog = tk.Toplevel(parent)
        dialog.title("Изменить правило" if index is not None else "Добавить правило")
        dialog.geometry("500x260")
        dialog.resizable(False, False)
        dialog.configure(bg=p["root"])
        dialog.transient(parent)
        dialog.grab_set()

        current = self.route_rules[index] if index is not None else {"type": "process", "value": "", "action": "proxy"}
        type_var = tk.StringVar(value=_RULE_TYPE_LABELS.get(current["type"], "Приложение"))
        value_var = tk.StringVar(value=current.get("value", ""))
        action_var = tk.StringVar(value=_RULE_ACTION_LABELS.get(current["action"], "VPN"))

        form = tk.Frame(dialog, bg=p["card"], highlightbackground=p["border"], highlightthickness=1)
        form.pack(fill="both", expand=True, padx=14, pady=14)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Тип", bg=p["card"], fg=p["text"]).grid(row=0, column=0, sticky="w", padx=12, pady=(14, 7))
        type_box = ttk.Combobox(form, textvariable=type_var, values=list(_RULE_TYPE_LABELS.values()), state="readonly", width=20)
        type_box.grid(row=0, column=1, sticky="ew", padx=(8, 12), pady=(14, 7))

        tk.Label(form, text="Значение", bg=p["card"], fg=p["text"]).grid(row=1, column=0, sticky="w", padx=12, pady=7)
        value_entry = tk.Entry(form, textvariable=value_var, bg=p["card2"], fg=p["text"], insertbackground=p["text"], relief="flat", bd=0)
        value_entry.grid(row=1, column=1, sticky="ew", padx=(8, 12), pady=7, ipady=6)

        tk.Label(form, text="Маршрут", bg=p["card"], fg=p["text"]).grid(row=2, column=0, sticky="w", padx=12, pady=7)
        action_box = ttk.Combobox(form, textvariable=action_var, values=list(_RULE_ACTION_LABELS.values()), state="readonly", width=20)
        action_box.grid(row=2, column=1, sticky="ew", padx=(8, 12), pady=7)

        hint = tk.Label(form, text="", bg=p["card"], fg=p["secondary"], font=("Segoe UI", 8), anchor="w")
        hint.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 7))

        def update_hint(*_):
            label = type_var.get()
            if label == "Приложение":
                hint.configure(text="Например: TheCrewMotorfest.exe")
            elif label == "Домен":
                hint.configure(text="Например: *.ubisoft.com или ubisoft.com")
            else:
                hint.configure(text="Например: 1.1.1.0/24 или 8.8.8.8")
        type_var.trace_add("write", update_hint)
        update_hint()

        actions = tk.Frame(dialog, bg=p["root"])
        actions.pack(fill="x", padx=14, pady=(0, 14))

        def save_rule():
            rule = {
                "type": _RULE_TYPE_KEYS.get(type_var.get(), "process"),
                "value": value_var.get().strip(),
                "action": _RULE_ACTION_KEYS.get(action_var.get(), "proxy"),
            }
            normalized = normalize_route_rules([rule])
            if not normalized:
                messagebox.showwarning("Маршрутизация", "Проверь значение правила.", parent=dialog)
                return
            rule = normalized[0]
            if index is None:
                self.route_rules.append(rule)
            else:
                self.route_rules[index] = rule
            self.route_rules = normalize_route_rules(self.route_rules)
            self._persist_route_rules()
            self._refresh_route_tree()
            try:
                self._append_log(f"[ROUTE] Правило сохранено: {rule['type']} {rule['value']} -> {rule['action']}")
            except Exception:
                pass
            dialog.destroy()

        tk.Button(
            actions, text="Сохранить", command=save_rule,
            bg=p["accent"], fg=p["accent_text"], activebackground=p["accent_hover"],
            activeforeground=p["accent_text"], relief="flat", bd=0, padx=14, pady=7,
        ).pack(side="right")
        tk.Button(
            actions, text="Отмена", command=dialog.destroy,
            bg=p["card2"], fg=p["text"], activebackground=p["segment_hover"],
            activeforeground=p["text"], relief="flat", bd=0, padx=14, pady=7,
        ).pack(side="right", padx=(0, 8))
        value_entry.focus_set()

    def _apply_routing_now(self) -> None:
        self._persist_route_rules()
        if getattr(self, "runner", None) and self.runner.running():
            try:
                self.routing_apply_hint.configure(text="Перезапускаю VPN с новыми правилами...")
            except Exception:
                pass
            self.apply_strategy()
        else:
            try:
                self.routing_apply_hint.configure(text="Сохранено. Правила применятся при следующем запуске VPN.")
            except Exception:
                pass

    def _build_core_settings(self, parent):
        p = self.palette
        frame = self._settings_page(parent, "Ядра", "Пути к sing-box и Xray, а также обслуживание компонентов.")
        box = tk.Frame(frame, bg=p["card2"], highlightbackground=p["border"], highlightthickness=1)
        box.pack(fill="x", padx=18, pady=(0, 12))
        box.grid_columnconfigure(0, weight=1)

        tk.Label(box, text="sing-box.exe", bg=p["card2"], fg=p["text"], font=("Segoe UI Semibold", 9)).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        tk.Entry(box, textvariable=self.singbox_var, bg=p["card"], fg=p["text"], insertbackground=p["text"], relief="flat", bd=0).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8), ipady=6)
        tk.Button(box, text="Обзор", command=self._browse_singbox, bg=p["segment"], fg=p["text"], relief="flat", bd=0, padx=12, pady=6).grid(row=1, column=1, padx=(0, 12), pady=(0, 8))

        tk.Label(box, text="xray.exe", bg=p["card2"], fg=p["text"], font=("Segoe UI Semibold", 9)).grid(row=2, column=0, sticky="w", padx=12, pady=(5, 4))
        tk.Entry(box, textvariable=self.xray_var, bg=p["card"], fg=p["text"], insertbackground=p["text"], relief="flat", bd=0).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12), ipady=6)
        tk.Button(box, text="Обзор", command=self._browse_xray, bg=p["segment"], fg=p["text"], relief="flat", bd=0, padx=12, pady=6).grid(row=3, column=1, padx=(0, 12), pady=(0, 12))

        actions = tk.Frame(frame, bg=p["card"])
        actions.pack(fill="x", padx=18)
        tk.Button(
            actions, text="Установить / обновить ядра", command=lambda: self._install_cores(manual=True),
            bg=p["accent"], fg=p["accent_text"], activebackground=p["accent_hover"],
            activeforeground=p["accent_text"], relief="flat", bd=0, padx=13, pady=7,
        ).pack(side="left")
        tk.Button(
            actions, text="Обновить списки", command=self._manual_update_lists,
            bg=p["card2"], fg=p["text"], activebackground=p["segment_hover"],
            activeforeground=p["text"], relief="flat", bd=0, padx=13, pady=7,
        ).pack(side="left", padx=(8, 0))
        return frame
