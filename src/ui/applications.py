# -*- coding: utf-8 -*-
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
