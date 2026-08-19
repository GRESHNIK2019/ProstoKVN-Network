# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app_config import STRATEGIES, STRATEGY_DESCRIPTIONS, THEME_LABELS
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


class SettingsMixin:
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
        window.geometry("980x660")
        window.minsize(840, 570)
        window.configure(bg=p["root"])
        window.transient(self)

        body = tk.Frame(window, bg=p["root"])
        body.pack(fill="both", expand=True, padx=14, pady=14)

        sidebar = tk.Frame(
            body,
            bg=p["card"],
            width=190,
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="Настройки",
            bg=p["card"],
            fg=p["text"],
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", padx=14, pady=(14, 12))

        content = tk.Frame(
            body,
            bg=p["card"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        content.pack(side="left", fill="both", expand=True)

        pages = {
            "general": self._build_general_settings(content),
            "routing": self._build_routing_settings(content),
            "cores": self._build_core_settings(content),
        }
        nav_buttons: dict[str, tk.Button] = {}

        def switch(name: str) -> None:
            if name not in pages:
                name = "routing"
            for frame in pages.values():
                frame.pack_forget()
            pages[name].pack(fill="both", expand=True)
            for key, button in nav_buttons.items():
                selected = key == name
                button.configure(
                    bg=p["accent"] if selected else p["card"],
                    fg=p["accent_text"] if selected else p["text"],
                )

        for key, label in (
            ("general", "Основные"),
            ("routing", "Маршрутизация"),
            ("cores", "Ядра"),
        ):
            button = tk.Button(
                sidebar,
                text=label,
                anchor="w",
                command=lambda k=key: switch(k),
                bg=p["card"],
                fg=p["text"],
                activebackground=p["segment_hover"],
                activeforeground=p["text"],
                relief="flat",
                bd=0,
                padx=14,
                pady=10,
                font=("Segoe UI", 10),
            )
            button.pack(fill="x", padx=6, pady=2)
            nav_buttons[key] = button

        self._settings_switch = switch
        switch(page)

    def _settings_page(self, parent, title: str, description: str):
        p = self.palette
        frame = tk.Frame(parent, bg=p["card"])
        tk.Label(
            frame,
            text=title,
            bg=p["card"],
            fg=p["text"],
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w", padx=18, pady=(18, 3))
        tk.Label(
            frame,
            text=description,
            bg=p["card"],
            fg=p["secondary"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=690,
        ).pack(anchor="w", padx=18, pady=(0, 14))
        return frame

    def _build_general_settings(self, parent):
        p = self.palette
        frame = self._settings_page(parent, "Основные", "Внешний вид и поведение приложения.")

        section = tk.Frame(
            frame,
            bg=p["card2"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        section.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(
            section,
            text="Тема",
            bg=p["card2"],
            fg=p["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", padx=12, pady=(12, 8))
        row = tk.Frame(section, bg=p["card2"])
        row.pack(anchor="w", padx=12, pady=(0, 12))
        self.theme_buttons = {}
        for key in ("system", "light", "dark"):
            button = tk.Button(
                row,
                text=THEME_LABELS[key],
                command=lambda k=key: self._set_theme_mode(k),
                bg=p["segment"],
                fg=p["text"],
                activebackground=p["segment_hover"],
                activeforeground=p["text"],
                relief="flat",
                bd=0,
                padx=12,
                pady=6,
            )
            button.pack(side="left", padx=(0, 6))
            self.theme_buttons[key] = button
        self._refresh_theme_buttons()

        auto = tk.Checkbutton(
            frame,
            text="Автопереподключение VPN при неожиданной остановке",
            variable=self.auto_reconnect_var,
            command=self._save_settings,
            bg=p["card"],
            fg=p["text"],
            activebackground=p["card"],
            activeforeground=p["text"],
            selectcolor=p["card2"],
            bd=0,
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

        mode_box = tk.Frame(
            frame,
            bg=p["card2"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        mode_box.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(
            mode_box,
            text="Режим маршрутизации",
            bg=p["card2"],
            fg=p["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", padx=12, pady=(12, 7))
        modes = tk.Frame(mode_box, bg=p["card2"])
        modes.pack(anchor="w", padx=12, pady=(0, 5))
        mode_buttons: dict[str, tk.Button] = {}

        desc = tk.Label(
            mode_box,
            bg=p["card2"],
            fg=p["secondary"],
            font=("Segoe UI", 9),
            anchor="w",
        )

        def select_mode(key: str) -> None:
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
                modes,
                text=STRATEGIES[key],
                command=lambda k=key: select_mode(k),
                bg=p["segment"],
                fg=p["text"],
                activebackground=p["segment_hover"],
                activeforeground=p["text"],
                relief="flat",
                bd=0,
                padx=14,
                pady=6,
            )
            button.pack(side="left", padx=(0, 6))
            mode_buttons[key] = button
        desc.pack(fill="x", padx=12, pady=(2, 12))
        select_mode(self.strategy_key_var.get())

        rules_box = tk.Frame(
            frame,
            bg=p["card2"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        rules_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        head = tk.Frame(rules_box, bg=p["card2"])
        head.pack(fill="x", padx=10, pady=(10, 8))
        tk.Label(
            head,
            text="Пользовательские правила",
            bg=p["card2"],
            fg=p["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        tk.Label(
            head,
            text="DIRECT / VPN / BLOCK",
            bg=p["card2"],
            fg=p["muted"],
            font=("Segoe UI", 8),
        ).pack(side="right")

        table_wrap = tk.Frame(rules_box, bg=p["card2"])
        table_wrap.pack(fill="both", expand=True, padx=10)
        tree = ttk.Treeview(
            table_wrap,
            columns=("type", "value", "action"),
            show="headings",
            selectmode="browse",
        )
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
            buttons,
            text="+ Добавить правило",
            command=self._add_route_rule,
            bg=p["accent"],
            fg=p["accent_text"],
            activebackground=p["accent_hover"],
            activeforeground=p["accent_text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Изменить",
            command=self._edit_route_rule,
            bg=p["segment"],
            fg=p["text"],
            activebackground=p["segment_hover"],
            activeforeground=p["text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).pack(side="left", padx=(7, 0))
        tk.Button(
            buttons,
            text="Удалить",
            command=self._remove_route_rule,
            bg=p["segment"],
            fg=p["bad"],
            activebackground=p["segment_hover"],
            activeforeground=p["bad"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).pack(side="left", padx=(7, 0))

        footer = tk.Frame(frame, bg=p["card"])
        footer.pack(fill="x", padx=18, pady=(0, 16))
        self.routing_apply_hint = tk.Label(
            footer,
            text="Изменения правил сохраняются автоматически.",
            bg=p["card"],
            fg=p["secondary"],
            font=("Segoe UI", 9),
        )
        self.routing_apply_hint.pack(side="left")
        tk.Button(
            footer,
            text="Применить к VPN",
            command=self._apply_routing_now,
            bg=p["accent"],
            fg=p["accent_text"],
            activebackground=p["accent_hover"],
            activeforeground=p["accent_text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
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
                "",
                "end",
                iid=str(index),
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

        current = (
            self.route_rules[index]
            if index is not None
            else {"type": "process", "value": "", "action": "proxy"}
        )
        type_var = tk.StringVar(value=_RULE_TYPE_LABELS.get(current["type"], "Приложение"))
        value_var = tk.StringVar(value=current.get("value", ""))
        action_var = tk.StringVar(value=_RULE_ACTION_LABELS.get(current["action"], "VPN"))

        form = tk.Frame(
            dialog,
            bg=p["card"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        form.pack(fill="both", expand=True, padx=14, pady=14)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Тип", bg=p["card"], fg=p["text"]).grid(
            row=0, column=0, sticky="w", padx=12, pady=(14, 7)
        )
        type_box = ttk.Combobox(
            form,
            textvariable=type_var,
            values=list(_RULE_TYPE_LABELS.values()),
            state="readonly",
            width=20,
        )
        type_box.grid(row=0, column=1, sticky="ew", padx=(8, 12), pady=(14, 7))

        tk.Label(form, text="Значение", bg=p["card"], fg=p["text"]).grid(
            row=1, column=0, sticky="w", padx=12, pady=7
        )
        value_entry = tk.Entry(
            form,
            textvariable=value_var,
            bg=p["card2"],
            fg=p["text"],
            insertbackground=p["text"],
            relief="flat",
            bd=0,
        )
        value_entry.grid(row=1, column=1, sticky="ew", padx=(8, 12), pady=7, ipady=6)

        tk.Label(form, text="Маршрут", bg=p["card"], fg=p["text"]).grid(
            row=2, column=0, sticky="w", padx=12, pady=7
        )
        action_box = ttk.Combobox(
            form,
            textvariable=action_var,
            values=list(_RULE_ACTION_LABELS.values()),
            state="readonly",
            width=20,
        )
        action_box.grid(row=2, column=1, sticky="ew", padx=(8, 12), pady=7)

        hint = tk.Label(
            form,
            text="",
            bg=p["card"],
            fg=p["secondary"],
            font=("Segoe UI", 8),
            anchor="w",
        )
        hint.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 7))

        def update_hint(*_) -> None:
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

        def save_rule() -> None:
            rule = {
                "type": _RULE_TYPE_KEYS.get(type_var.get(), "process"),
                "value": value_var.get().strip(),
                "action": _RULE_ACTION_KEYS.get(action_var.get(), "proxy"),
            }
            normalized = normalize_route_rules([rule])
            if not normalized:
                messagebox.showwarning(
                    "Маршрутизация",
                    "Проверь значение правила.",
                    parent=dialog,
                )
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
                self._append_log(
                    f"[ROUTE] Правило сохранено: {rule['type']} {rule['value']} -> {rule['action']}"
                )
            except Exception:
                pass
            dialog.destroy()

        tk.Button(
            actions,
            text="Сохранить",
            command=save_rule,
            bg=p["accent"],
            fg=p["accent_text"],
            activebackground=p["accent_hover"],
            activeforeground=p["accent_text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
        ).pack(side="right")
        tk.Button(
            actions,
            text="Отмена",
            command=dialog.destroy,
            bg=p["card2"],
            fg=p["text"],
            activebackground=p["segment_hover"],
            activeforeground=p["text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
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
                self.routing_apply_hint.configure(
                    text="Сохранено. Правила применятся при следующем запуске VPN."
                )
            except Exception:
                pass

    def _build_core_settings(self, parent):
        p = self.palette
        frame = self._settings_page(
            parent,
            "Ядра",
            "Пути к sing-box и Xray, а также обслуживание компонентов.",
        )
        box = tk.Frame(
            frame,
            bg=p["card2"],
            highlightbackground=p["border"],
            highlightthickness=1,
        )
        box.pack(fill="x", padx=18, pady=(0, 12))
        box.grid_columnconfigure(0, weight=1)

        tk.Label(
            box,
            text="sing-box.exe",
            bg=p["card2"],
            fg=p["text"],
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        tk.Entry(
            box,
            textvariable=self.singbox_var,
            bg=p["card"],
            fg=p["text"],
            insertbackground=p["text"],
            relief="flat",
            bd=0,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8), ipady=6)
        tk.Button(
            box,
            text="Обзор",
            command=self._browse_singbox,
            bg=p["segment"],
            fg=p["text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).grid(row=1, column=1, padx=(0, 12), pady=(0, 8))

        tk.Label(
            box,
            text="xray.exe",
            bg=p["card2"],
            fg=p["text"],
            font=("Segoe UI Semibold", 9),
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(5, 4))
        tk.Entry(
            box,
            textvariable=self.xray_var,
            bg=p["card"],
            fg=p["text"],
            insertbackground=p["text"],
            relief="flat",
            bd=0,
        ).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12), ipady=6)
        tk.Button(
            box,
            text="Обзор",
            command=self._browse_xray,
            bg=p["segment"],
            fg=p["text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).grid(row=3, column=1, padx=(0, 12), pady=(0, 12))

        actions = tk.Frame(frame, bg=p["card"])
        actions.pack(fill="x", padx=18)
        tk.Button(
            actions,
            text="Установить / обновить ядра",
            command=lambda: self._install_cores(manual=True),
            bg=p["accent"],
            fg=p["accent_text"],
            activebackground=p["accent_hover"],
            activeforeground=p["accent_text"],
            relief="flat",
            bd=0,
            padx=13,
            pady=7,
        ).pack(side="left")
        tk.Button(
            actions,
            text="Обновить списки",
            command=self._manual_update_lists,
            bg=p["card2"],
            fg=p["text"],
            activebackground=p["segment_hover"],
            activeforeground=p["text"],
            relief="flat",
            bd=0,
            padx=13,
            pady=7,
        ).pack(side="left", padx=(8, 0))
        return frame
