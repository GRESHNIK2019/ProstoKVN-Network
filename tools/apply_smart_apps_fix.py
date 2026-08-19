# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APPLICATIONS = r'''# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from routing import is_reserved_direct_process, normalize_process_names


class ApplicationMixin:
    def _refresh_custom_apps_label(self):
        if not hasattr(self, "custom_apps_var"):
            return
        if not self.custom_vpn_processes:
            self.custom_apps_var.set("Приложения VPN: не выбраны")
            return

        preview = ", ".join(self.custom_vpn_processes[:3])
        if len(self.custom_vpn_processes) > 3:
            preview += f" +{len(self.custom_vpn_processes) - 3}"
        self.custom_apps_var.set(f"Приложения VPN: {preview}")

    def open_app_manager(self):
        p = self.palette
        window = tk.Toplevel(self)
        window.title("Приложения через VPN")
        window.geometry("620x470")
        window.minsize(540, 400)
        window.configure(bg=p["root"])
        window.transient(self)

        tk.Label(
            window,
            text="Добавь имя процесса, который должен работать через VPN.",
            bg=p["root"],
            fg=p["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", padx=14, pady=(14, 2))
        tk.Label(
            window,
            text="Например: game.exe или launcher.exe. Если .exe не указать, оно добавится автоматически.",
            bg=p["root"],
            fg=p["secondary"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=14, pady=(0, 10))

        add_row = tk.Frame(window, bg=p["root"])
        add_row.pack(fill="x", padx=14, pady=(0, 10))

        self.app_process_var = tk.StringVar()
        entry = tk.Entry(
            add_row,
            textvariable=self.app_process_var,
            bg=p["card2"],
            fg=p["text"],
            insertbackground=p["text"],
            relief="flat",
            bd=0,
            font=("Consolas", 10),
        )
        entry.pack(side="left", fill="x", expand=True, ipady=7)
        entry.bind("<Return>", lambda _event: self._add_vpn_app())

        tk.Button(
            add_row,
            text="Добавить процесс",
            command=self._add_vpn_app,
            bg=p["accent"],
            fg=p["accent_text"],
            activebackground=p["accent_hover"],
            activeforeground=p["accent_text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=7,
        ).pack(side="left", padx=(8, 0))

        frame = tk.Frame(window, bg=p["card"], highlightbackground=p["border"], highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.app_listbox = tk.Listbox(
            frame,
            bg=p["card"],
            fg=p["text"],
            selectbackground=p["selection"],
            relief="flat",
            bd=0,
            font=("Consolas", 10),
        )
        self.app_listbox.pack(fill="both", expand=True, padx=8, pady=8)
        self._refresh_app_listbox()

        buttons = tk.Frame(window, bg=p["root"])
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(
            buttons,
            text="Удалить выбранный",
            command=self._remove_vpn_app,
            bg=p["card2"],
            fg=p["text"],
            activebackground=p["segment_hover"],
            activeforeground=p["text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Закрыть",
            command=window.destroy,
            bg=p["card2"],
            fg=p["text"],
            activebackground=p["segment_hover"],
            activeforeground=p["text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
        ).pack(side="right")

        entry.focus_set()

    def _refresh_app_listbox(self):
        listbox = getattr(self, "app_listbox", None)
        if not listbox or not listbox.winfo_exists():
            return
        listbox.delete(0, "end")
        for name in self.custom_vpn_processes:
            listbox.insert("end", name)

    def _add_vpn_app(self):
        process_var = getattr(self, "app_process_var", None)
        raw_name = process_var.get().strip() if process_var else ""
        names = normalize_process_names([raw_name])
        if not names:
            messagebox.showwarning("Приложения VPN", "Введи имя процесса, например game.exe.")
            return

        name = names[0]
        if is_reserved_direct_process(name):
            messagebox.showwarning(
                "Приложения VPN",
                f"{name} зарезервирован как DIRECT и не может быть добавлен в VPN.",
            )
            return

        old_names = {item.lower() for item in self.custom_vpn_processes}
        if name.lower() in old_names:
            messagebox.showinfo("Приложения VPN", f"{name} уже есть в списке.")
            return

        self.custom_vpn_processes = normalize_process_names(self.custom_vpn_processes + [name])
        self._save_settings()
        self._refresh_custom_apps_label()
        self._refresh_app_listbox()
        self._append_log(f"[ROUTE] Добавлен процесс через VPN: {name}")
        process_var.set("")

    def _remove_vpn_app(self):
        listbox = getattr(self, "app_listbox", None)
        if not listbox or not listbox.winfo_exists():
            return
        selection = listbox.curselection()
        if not selection:
            return

        name = str(listbox.get(selection[0]))
        self.custom_vpn_processes = [
            item for item in self.custom_vpn_processes
            if item.lower() != name.lower()
        ]
        self._save_settings()
        self._refresh_custom_apps_label()
        self._refresh_app_listbox()
        self._append_log(f"[ROUTE] Удалён процесс из VPN: {name}")
'''

TESTS = r'''# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from routing import (
    UBISOFT_DOMAIN_SUFFIXES,
    UBISOFT_SMART_PROCESSES,
    build_route_rules,
    is_reserved_direct_process,
)


class SmartAppsTests(unittest.TestCase):
    def test_smart_has_ubisoft_profile(self):
        rules, _, final = build_route_rules("smart_ru")
        self.assertEqual(final, "direct")
        self.assertTrue(any(rule.get("process_name") == UBISOFT_SMART_PROCESSES and rule.get("outbound") == "proxy" for rule in rules))
        self.assertTrue(any(rule.get("domain_suffix") == UBISOFT_DOMAIN_SUFFIXES and rule.get("outbound") == "proxy" for rule in rules))

    def test_apps_mode_only_uses_manual_processes(self):
        rules, _, _ = build_route_rules("game_only", custom_vpn_processes=["client"])
        self.assertTrue(any(rule.get("process_name") == ["client.exe"] and rule.get("outbound") == "proxy" for rule in rules))
        self.assertFalse(any("Discord.exe" in rule.get("process_name", []) for rule in rules))
        self.assertFalse(any("Telegram.exe" in rule.get("process_name", []) for rule in rules))
        self.assertFalse(any(rule.get("process_name") == UBISOFT_SMART_PROCESSES for rule in rules))

    def test_ru_direct_is_before_manual_process(self):
        rules, _, _ = build_route_rules("smart_ru", custom_vpn_processes=["browser.exe"])
        ru_index = next(i for i, rule in enumerate(rules) if ".ru" in rule.get("domain_suffix", []))
        app_index = next(i for i, rule in enumerate(rules) if rule.get("process_name") == ["browser.exe"])
        self.assertLess(ru_index, app_index)

    def test_reserved_direct_process(self):
        self.assertTrue(is_reserved_direct_process("steam"))
        self.assertFalse(is_reserved_direct_process("game"))


if __name__ == "__main__":
    unittest.main()
'''

routing_path = ROOT / "src/routing.py"
routing = routing_path.read_text(encoding="utf-8")

constants_old = 'TELEGRAM_PROCESSES = ["Telegram.exe"]\nRU_DIRECT_DOMAIN_SUFFIXES = [".ru", ".su", ".рф", ".xn--p1ai"]'
constants_new = '''TELEGRAM_PROCESSES = ["Telegram.exe"]

UBISOFT_SMART_PROCESSES = [
    "UbisoftConnect.exe",
    "UbisoftConnectWebCore.exe",
    "UbisoftGameLauncher.exe",
    "UbisoftGameLauncher64.exe",
    "UplayWebCore.exe",
    "UplayService.exe",
    "upc.exe",
    "BEService.exe",
    "BEService_x64.exe",
    "TheCrew" + "Motor" + "fest.exe",
    "TheCrew" + "Motor" + "fest_BE.exe",
]
UBISOFT_DOMAIN_SUFFIXES = [
    ".ubisoft.com",
    ".ubi.com",
    ".ubisoftconnect.com",
    ".uplay.com",
]
RU_DIRECT_DOMAIN_SUFFIXES = [".ru", ".su", ".рф", ".xn--p1ai"]'''
if constants_old not in routing:
    raise SystemExit("Не найден блок констант routing.py")
routing = routing.replace(constants_old, constants_new, 1)

old_logic = '''    custom = normalize_process_names(custom_vpn_processes or [])
    if custom:
        rules.append({"process_name": custom, "action": "route", "outbound": "proxy"})

    if route_mode in {"smart_ru", "game_only"} or discord_vpn:
        rules.append({"process_name": DISCORD_PROCESSES, "action": "route", "outbound": "proxy"})

    if route_mode == "smart_ru":
        rules.append({"process_name": TELEGRAM_PROCESSES, "action": "route", "outbound": "proxy"})

    if steam_webhelper_vpn:
        rules.append({"process_name": ["steamwebhelper.exe"], "action": "route", "outbound": "proxy"})

    # Российские доменные зоны остаются напрямую во всех стратегиях.
    rules.append({
        "domain_suffix": RU_DIRECT_DOMAIN_SUFFIXES,
        "action": "route",
        "outbound": "direct",
    })
'''
new_logic = '''    # Российские домены имеют приоритет над правилами приложений.
    rules.append({
        "domain_suffix": RU_DIRECT_DOMAIN_SUFFIXES,
        "action": "route",
        "outbound": "direct",
    })

    custom = normalize_process_names(custom_vpn_processes or [])

    if route_mode == "smart_ru":
        if custom:
            rules.append({"process_name": custom, "action": "route", "outbound": "proxy"})
        if discord_vpn:
            rules.append({"process_name": DISCORD_PROCESSES, "action": "route", "outbound": "proxy"})
        rules.append({"process_name": TELEGRAM_PROCESSES, "action": "route", "outbound": "proxy"})
        rules.append({"process_name": UBISOFT_SMART_PROCESSES, "action": "route", "outbound": "proxy"})
        rules.append({"domain_suffix": UBISOFT_DOMAIN_SUFFIXES, "action": "route", "outbound": "proxy"})

    elif route_mode == "game_only":
        # В «Приложениях» через VPN идут только процессы, добавленные пользователем.
        if custom:
            rules.append({"process_name": custom, "action": "route", "outbound": "proxy"})

    if steam_webhelper_vpn:
        rules.append({"process_name": ["steamwebhelper.exe"], "action": "route", "outbound": "proxy"})
'''
if old_logic not in routing:
    raise SystemExit("Не найден блок маршрутизации")
routing = routing.replace(old_logic, new_logic, 1)

helper_marker = "\n\ndef _rule_sets_for_paths"
helper = '''

def is_reserved_direct_process(value: str) -> bool:
    names = normalize_process_names([value])
    if not names:
        return False
    reserved = {name.lower() for name in PROTECTED_DIRECT + STEAM_DIRECT}
    return names[0].lower() in reserved
'''
if "def is_reserved_direct_process" not in routing:
    routing = routing.replace(helper_marker, helper + helper_marker, 1)
routing_path.write_text(routing, encoding="utf-8")

(ROOT / "src/ui/applications.py").write_text(APPLICATIONS, encoding="utf-8")

app_path = ROOT / "src/ProstoKVNNetwork.pyw"
app = app_path.read_text(encoding="utf-8")
app = app.replace(
    "from ui.subscriptions import SubscriptionMixin\nfrom ui.theme import ThemeMixin\n",
    "from ui.applications import ApplicationMixin\nfrom ui.subscriptions import SubscriptionMixin\nfrom ui.theme import ThemeMixin\n",
    1,
)
app = app.replace(
    "class App(ThemeMixin, SubscriptionMixin, tk.Tk):",
    "class App(ThemeMixin, SubscriptionMixin, ApplicationMixin, tk.Tk):",
    1,
)
start = app.find("    # ---------------- Приложения и watchdog ----------------\n")
watch = app.find("    def _poll_runner_health(self):", start)
if start < 0 or watch < 0:
    raise SystemExit("Не найден старый менеджер приложений")
app = app[:start] + "    # ---------------- Приложения и watchdog ----------------\n" + app[watch:]
app_path.write_text(app, encoding="utf-8")

config_path = ROOT / "src/app_config.py"
config = config_path.read_text(encoding="utf-8")
config = config.replace(
    '"smart_ru": "Блокируемые сервисы + выбранные приложения через VPN, российские сайты напрямую",',
    '"smart_ru": "Блокируемые сервисы, Ubisoft и выбранные процессы через VPN; российские сайты напрямую",',
)
config = config.replace(
    '"game_only": "Только выбранные приложения и Discord через VPN",',
    '"game_only": "Только процессы, которые пользователь добавил вручную",',
)
config_path.write_text(config, encoding="utf-8")

(ROOT / "tests/test_smart_apps.py").write_text(TESTS, encoding="utf-8")
print("Smart/Applications fix applied")
