# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from subscriptions import Subscription, new_subscription


class SubscriptionMixin:
    def _active_subscription(self) -> Subscription | None:
        for item in self.subscriptions:
            if item.id == self.active_subscription_id:
                return item
        return self.subscriptions[0] if self.subscriptions else None

    def _load_active_subscription_vars(self) -> None:
        item = self._active_subscription()
        if not item:
            item = new_subscription("import_sub")
            self.subscriptions = [item]
            self.active_subscription_id = item.id

        self.url_var.set(item.url)
        self.subscription_name_var.set(item.name)
        self.subscription_enabled_var.set(bool(item.enabled))
        self.subscription_interval_var.set(str(item.update_interval or "0"))
        self.subscription_sort_var.set(str(item.sort_order or "1"))

    def _store_active_subscription_from_vars(self) -> None:
        item = self._active_subscription()
        if not item:
            return
        item.name = (self.subscription_name_var.get() or "Подписка").strip() or "Подписка"
        item.url = self.url_var.get().strip()
        item.enabled = bool(self.subscription_enabled_var.get())
        item.update_interval = self.subscription_interval_var.get().strip() or "0"
        item.sort_order = self.subscription_sort_var.get().strip() or "1"

    def _subscription_info_text(self) -> str:
        item = self._active_subscription()
        if not item:
            return "Подписки не настроены"
        enabled = "On" if item.enabled else "Off"
        return f"{item.name}  |  URL скрыт  |  {enabled}  |  групп: {len(self.subscriptions)}"

    def _refresh_subscription_info(self) -> None:
        if hasattr(self, "subscription_info"):
            self.subscription_info.config(text=self._subscription_info_text())

    @staticmethod
    def _masked_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        if len(url) <= 30:
            return url
        return url[:24] + "..." + url[-5:]

    def _selected_subscription_id(self) -> str | None:
        tree = getattr(self, "sub_list_tree", None)
        if not tree or not tree.winfo_exists():
            return None
        selection = tree.selection()
        return selection[0] if selection else None

    def _find_subscription(self, subscription_id: str | None) -> Subscription | None:
        if not subscription_id:
            return None
        for item in self.subscriptions:
            if item.id == subscription_id:
                return item
        return None

    def open_subscription_manager(self) -> None:
        palette = self.palette
        if self.sub_window and self.sub_window.winfo_exists():
            self.sub_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.sub_window = window
        window.title("Группы подписок")
        window.geometry("1040x540")
        window.minsize(900, 480)
        window.configure(bg=palette["root"])
        window.transient(self)

        top = tk.Frame(window, bg=palette["root"])
        top.pack(fill="x", padx=12, pady=(10, 6))

        def button(text, command, primary=False):
            return tk.Button(
                top,
                text=text,
                command=command,
                bg=palette["accent"] if primary else palette["card2"],
                fg=palette["accent_text"] if primary else palette["text"],
                activebackground=palette["accent_hover"] if primary else palette["segment_hover"],
                activeforeground=palette["accent_text"] if primary else palette["text"],
                relief="flat",
                bd=0,
                padx=12,
                pady=6,
            )

        button("Добавить", lambda: self.open_subscription_editor(new_item=True)).pack(side="left")
        button("Редактировать", self.open_subscription_editor).pack(side="left", padx=(8, 0))
        button("Сделать активной", self._activate_selected_subscription).pack(side="left", padx=(8, 0))
        button("Удалить", self._delete_selected_subscription).pack(side="left", padx=(8, 0))
        button("Обновить активную", self.refresh_current_subscription_from_manager, primary=True).pack(side="left", padx=(8, 0))
        button("Закрыть", window.destroy).pack(side="right")

        table_frame = tk.Frame(
            window,
            bg=palette["card"],
            highlightbackground=palette["border"],
            highlightthickness=1,
        )
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("alias", "url", "enabled", "interval", "sort", "active")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("alias", text="Псевдоним")
        tree.heading("url", text="URL")
        tree.heading("enabled", text="Включена")
        tree.heading("interval", text="Интервал")
        tree.heading("sort", text="Сортировка")
        tree.heading("active", text="Активная")
        tree.column("alias", width=210, anchor="w")
        tree.column("url", width=430, anchor="w")
        tree.column("enabled", width=90, anchor="center")
        tree.column("interval", width=90, anchor="center")
        tree.column("sort", width=90, anchor="center")
        tree.column("active", width=90, anchor="center")
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        tree.bind("<Double-Button-1>", lambda _event: self.open_subscription_editor())

        self.sub_list_tree = tree
        self._refresh_subscription_list()

    def _refresh_subscription_list(self) -> None:
        tree = getattr(self, "sub_list_tree", None)
        if not tree or not tree.winfo_exists():
            return

        for row in tree.get_children():
            tree.delete(row)

        ordered = sorted(
            self.subscriptions,
            key=lambda item: (self._safe_sort_value(item.sort_order), item.name.lower()),
        )
        for item in ordered:
            tree.insert(
                "",
                "end",
                iid=item.id,
                values=(
                    item.name,
                    self._masked_url(item.url),
                    "✓" if item.enabled else "",
                    item.update_interval,
                    item.sort_order,
                    "✓" if item.id == self.active_subscription_id else "",
                ),
            )

        if self.active_subscription_id and tree.exists(self.active_subscription_id):
            tree.selection_set(self.active_subscription_id)
            tree.see(self.active_subscription_id)

    @staticmethod
    def _safe_sort_value(value: str) -> int:
        try:
            return int(value)
        except Exception:
            return 999999

    def _activate_selected_subscription(self) -> None:
        subscription_id = self._selected_subscription_id()
        item = self._find_subscription(subscription_id)
        if not item:
            return

        self._store_active_subscription_from_vars()
        self.active_subscription_id = item.id
        self._load_active_subscription_vars()
        self._save_settings()
        self._refresh_subscription_info()
        self._refresh_subscription_list()
        self._append_log(f"[SUB] Активная группа: {item.name}")

    def _delete_selected_subscription(self) -> None:
        subscription_id = self._selected_subscription_id()
        item = self._find_subscription(subscription_id)
        if not item:
            return

        if not messagebox.askyesno("ProstoKVN Network", f"Удалить подписку «{item.name}»?"):
            return

        self.subscriptions = [sub for sub in self.subscriptions if sub.id != item.id]
        if not self.subscriptions:
            self.subscriptions.append(new_subscription("import_sub"))

        if self.active_subscription_id == item.id:
            self.active_subscription_id = self.subscriptions[0].id
            self._load_active_subscription_vars()

        self._save_settings()
        self._refresh_subscription_info()
        self._refresh_subscription_list()
        self._append_log(f"[SUB] Удалена группа: {item.name}")

    def open_subscription_editor(self, new_item: bool = False) -> None:
        palette = self.palette
        if self.sub_editor and self.sub_editor.winfo_exists():
            self.sub_editor.focus_force()
            return

        current = None if new_item else self._find_subscription(self._selected_subscription_id())
        if current is None and not new_item:
            current = self._active_subscription()

        source = current or new_subscription("Новая подписка")
        window = tk.Toplevel(self)
        self.sub_editor = window
        window.title("Новая подписка" if new_item else "Редактирование подписки")
        window.geometry("760x470")
        window.minsize(700, 430)
        window.configure(bg=palette["root"])
        window.transient(self)

        name_var = tk.StringVar(value=source.name)
        url_var = tk.StringVar(value=source.url)
        enabled_var = tk.BooleanVar(value=source.enabled)
        interval_var = tk.StringVar(value=source.update_interval)
        sort_var = tk.StringVar(value=source.sort_order)

        content = tk.Frame(window, bg=palette["root"])
        content.pack(fill="both", expand=True, padx=16, pady=16)
        content.grid_columnconfigure(1, weight=1)

        def add_row(row: int, label: str, widget) -> None:
            tk.Label(
                content,
                text=label,
                bg=palette["root"],
                fg=palette["text"],
                font=("Segoe UI Semibold", 10),
            ).grid(row=row, column=0, sticky="w", pady=8)
            widget.grid(row=row, column=1, sticky="ew", pady=8)

        name_entry = tk.Entry(
            content,
            textvariable=name_var,
            bg=palette["card2"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief="flat",
            font=("Segoe UI", 11),
            bd=0,
        )
        add_row(0, "Псевдоним", name_entry)

        url_entry = tk.Entry(
            content,
            textvariable=url_var,
            bg=palette["card2"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief="flat",
            font=("Consolas", 10),
            bd=0,
        )
        add_row(1, "URL", url_entry)

        enabled = tk.Checkbutton(
            content,
            text="Использовать эту подписку",
            variable=enabled_var,
            bg=palette["root"],
            fg=palette["text"],
            activebackground=palette["root"],
            activeforeground=palette["text"],
            selectcolor=palette["card2"],
            bd=0,
        )
        add_row(2, "Состояние", enabled)

        interval_entry = tk.Entry(
            content,
            textvariable=interval_var,
            bg=palette["card2"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief="flat",
            font=("Segoe UI", 11),
            bd=0,
        )
        add_row(3, "Интервал обновления", interval_entry)

        sort_entry = tk.Entry(
            content,
            textvariable=sort_var,
            bg=palette["card2"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief="flat",
            font=("Segoe UI", 11),
            bd=0,
        )
        add_row(4, "Сортировка", sort_entry)

        tk.Label(
            content,
            text="URL шифруется через Windows DPAPI перед сохранением в settings.json.",
            bg=palette["root"],
            fg=palette["muted"],
            font=("Segoe UI", 9),
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = tk.Frame(content, bg=palette["root"])
        buttons.grid(row=6, column=0, columnspan=2, pady=(24, 0))

        def save(refresh_now: bool = False) -> None:
            name = name_var.get().strip() or "Подписка"
            url = url_var.get().strip()
            if url and not url.startswith(("http://", "https://")):
                messagebox.showwarning("ProstoKVN Network", "URL подписки должен начинаться с http:// или https://")
                return

            if new_item:
                item = new_subscription(name, url)
                self.subscriptions.append(item)
            else:
                item = current
                if item is None:
                    return
                item.name = name
                item.url = url

            item.enabled = bool(enabled_var.get())
            item.update_interval = interval_var.get().strip() or "0"
            item.sort_order = sort_var.get().strip() or "1"
            self.active_subscription_id = item.id
            self._load_active_subscription_vars()
            self._save_settings()
            self._refresh_subscription_info()
            self._refresh_subscription_list()
            self._append_log(f"[SUB] Сохранена группа: {item.name}")
            window.destroy()

            if refresh_now and item.url:
                self.after(100, lambda: self.start_test(auto=False))

        tk.Button(
            buttons,
            text="Сохранить",
            command=lambda: save(False),
            bg=palette["accent"],
            fg=palette["accent_text"],
            activebackground=palette["accent_hover"],
            activeforeground=palette["accent_text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Сохранить и обновить",
            command=lambda: save(True),
            bg=palette["card2"],
            fg=palette["text"],
            activebackground=palette["segment_hover"],
            activeforeground=palette["text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons,
            text="Отмена",
            command=window.destroy,
            bg=palette["card2"],
            fg=palette["text"],
            activebackground=palette["segment_hover"],
            activeforeground=palette["text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
        ).pack(side="left", padx=(8, 0))

    def refresh_current_subscription_from_manager(self) -> None:
        self._store_active_subscription_from_vars()
        self._save_settings()
        item = self._active_subscription()
        if not item or not item.url:
            messagebox.showwarning("ProstoKVN Network", "У активной подписки нет URL.")
            return
        if not item.enabled:
            messagebox.showwarning("ProstoKVN Network", "Активная подписка выключена.")
            return

        self._refresh_subscription_info()
        self._append_log(f"[SUB] Обновляю активную группу: {item.name}")
        self.start_test(auto=False)
