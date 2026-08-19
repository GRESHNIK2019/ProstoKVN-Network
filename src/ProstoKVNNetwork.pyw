# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_config import (
    APP_VERSION, PALETTES, STRATEGIES, STRATEGY_DESCRIPTIONS, THEME_LABELS,
    UPDATE_API, UPDATE_ASSET, UPDATE_HASH_ASSET, detect_windows_theme,
)
from blocklists import blocklists_age_seconds, get_cached_ru_blocklists, update_ru_blocklists
from cores import find_singbox_binary, find_xray_binary, install_official_cores
from node_tester import test_node
from nodes import Node, download_subscription
from paths import SETTINGS_PATH
from routing import normalize_process_names
from settings_store import load_settings, save_settings
from subscriptions import dump_subscriptions, load_subscriptions, touch_subscription
from ui.subscriptions import SubscriptionMixin
from ui.theme import ThemeMixin
from updater import check_latest_release, download_update, launch_self_updater
from vpn_runner import TunRunner, is_admin

APP_DIR = Path(__file__).resolve().parent


def relaunch_as_admin() -> bool:
    if os.name != 'nt' or is_admin():
        return False
    try:
        params = f'"{Path(__file__).resolve()}"'
        rc = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, str(APP_DIR), 1)
        return int(rc) > 32
    except Exception:
        return False


if os.name == 'nt' and not is_admin():
    if relaunch_as_admin():
        raise SystemExit(0)


class App(ThemeMixin, SubscriptionMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.nodes: list[Node] = []
        self.tested_nodes: list[Node] = []
        self.selected_node: Node | None = None
        self.applied_node: Node | None = None
        self.runner: TunRunner | None = None
        self.singbox: Path | None = None
        self.xray: Path | None = None
        self.busy = False
        self.advanced_open = False
        self.applied_strategy_key: str | None = None
        self.blocklist_paths = get_cached_ru_blocklists()
        self.subscriptions = []
        self.active_subscription_id = ''
        self.custom_vpn_processes: list[str] = []
        self._auto_reconnect_attempted = False

        self.url_var = tk.StringVar()
        self.subscription_name_var = tk.StringVar(value='import_sub')
        self.subscription_enabled_var = tk.BooleanVar(value=True)
        self.subscription_interval_var = tk.StringVar(value='0')
        self.subscription_sort_var = tk.StringVar(value='1')
        self.filter_var = tk.StringVar()
        self.sub_window = None
        self.sub_editor = None
        self.strategy_key_var = tk.StringVar(value='smart_ru')
        self.theme_mode_var = tk.StringVar(value='system')
        self.status_var = tk.StringVar(value='Готово')
        self.best_var = tk.StringVar(value='Узел: —')
        self.node_info_var = tk.StringVar(value='—')
        self.route_info_var = tk.StringVar(value='—')
        self.strategy_info_var = tk.StringVar(value='—')
        self.state_info_var = tk.StringVar(value='Ожидание')
        self.singbox_var = tk.StringVar()
        self.xray_var = tk.StringVar()
        self.block_var = tk.StringVar(value='Списки: —')
        self.custom_apps_var = tk.StringVar(value='Приложения VPN: —')
        self.engine_var = tk.StringVar(value='Ядро: —')
        self.auto_reconnect_var = tk.BooleanVar(value=True)
        self.admin_var = tk.StringVar(value='Admin ✓' if is_admin() else 'Admin ✕')

        self._load_settings()
        self.current_theme = self._resolved_theme()
        self.palette = PALETTES[self.current_theme]

        self.title(f'ProstoKVN Network v{APP_VERSION}')
        self.geometry('1260x760')
        self.minsize(1040, 640)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        self._style()
        self._build()
        self.after(80, self._sync_titlebar_theme)
        self.after(100, self._drain)
        self.after(300, self._auto_find_cores)
        self.after(650, self._first_run_core_check)
        self.after(1100, self._auto_update_lists)
        self.after(2200, self._autoload_saved_subscription)
        self.after(4500, lambda: self.check_for_updates(manual=False))
        self.after(1500, self._poll_system_theme)
        self.after(1800, self._poll_runner_health)

    # ---------------- Тема ----------------






    # ---------------- Интерфейс ----------------
    def _menu_button(self, parent, text, active=False, command=None):
        p = self.palette
        bg = p['card'] if active else p['root']
        fg = p['text'] if active else p['secondary']
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg, cursor='hand2' if command else 'arrow', font=('Segoe UI', 10, 'bold' if active else 'normal'), padx=10, pady=6)
        lbl.pack(side='left', padx=(0, 8))
        if command:
            lbl.bind('<Button-1>', lambda _e: command())
        return lbl

    def _build(self):
        p = self.palette
        outer = tk.Frame(self, bg=p['root'])
        outer.pack(fill='both', expand=True)

        # Верхнее меню
        top = tk.Frame(outer, bg=p['root'])
        top.pack(fill='x', padx=12, pady=(8, 4))
        self._menu_button(top, 'Серверы', active=True)
        self._menu_button(top, 'Группа подписки', command=self.open_subscription_manager)
        self._menu_button(top, 'Настройки')
        self._menu_button(top, 'Помощь', command=lambda: self.check_for_updates(manual=True))

        right_top = tk.Frame(top, bg=p['root'])
        right_top.pack(side='right')
        pill = tk.Label(right_top, text='Steam.exe DIRECT', bg=p['good_bg'], fg=p['good'], font=('Segoe UI Semibold', 9), padx=10, pady=5)
        pill.pack(side='right', padx=(10, 0))

        # Панель действий
        toolbar = tk.Frame(outer, bg=p['card'], highlightbackground=p['border'], highlightthickness=1)
        toolbar.pack(fill='x', padx=12, pady=(0, 8))

        sub_row = tk.Frame(toolbar, bg=p['card'])
        sub_row.pack(fill='x', padx=10, pady=(10, 8))
        tk.Label(sub_row, text='Группа подписки', bg=p['card'], fg=p['text'], font=('Segoe UI Semibold', 10)).pack(side='left')
        self.subscription_info = tk.Label(sub_row, text=self._subscription_info_text(), anchor='w', bg=p['card2'], fg=p['text'], font=('Segoe UI', 10), padx=10, pady=8)
        self.subscription_info.pack(side='left', fill='x', expand=True, padx=(10, 8))
        tk.Button(sub_row, text='Управлять', command=self.open_subscription_manager, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=6).pack(side='left', padx=(0, 8))
        tk.Button(sub_row, text='Обновить подписку', command=self.start_test, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=6).pack(side='left')

        action_row = tk.Frame(toolbar, bg=p['card'])
        action_row.pack(fill='x', padx=10, pady=(0, 10))
        self.test_btn = tk.Button(action_row, text='Обновить узлы', command=self.start_test, bg=p['accent'], fg=p['accent_text'], activebackground=p['accent_hover'], activeforeground=p['accent_text'], relief='flat', bd=0, padx=14, pady=7)
        self.test_btn.pack(side='left')
        self.start_btn = tk.Button(action_row, text='Запустить VPN', command=self.start_vpn, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=14, pady=7, state='disabled')
        self.start_btn.pack(side='left', padx=(8, 0))
        self.apply_btn = tk.Button(action_row, text='Применить стратегию', command=self.apply_strategy, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=14, pady=7, state='disabled')
        self.apply_btn.pack(side='left', padx=(8, 0))
        self.stop_btn = tk.Button(action_row, text='Остановить', command=self.stop_vpn, bg=p['card2'], fg=p['bad'], activebackground=p['segment_hover'], activeforeground=p['bad'], relief='flat', bd=0, padx=14, pady=7, state='disabled')
        self.stop_btn.pack(side='left', padx=(8, 0))

        tk.Label(action_row, text='Фильтр', bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9)).pack(side='left', padx=(18, 6))
        self.filter_entry = tk.Entry(action_row, textvariable=self.filter_var, bg=p['card2'], fg=p['text'], insertbackground=p['text'], relief='flat', font=('Segoe UI', 10), bd=0, width=28)
        self.filter_entry.pack(side='left', padx=(0, 12), ipady=6)
        self.filter_var.trace_add('write', lambda *_: self._refresh_tree())

        strat_wrap = tk.Frame(action_row, bg=p['segment'], highlightbackground=p['border'], highlightthickness=1)
        strat_wrap.pack(side='right', padx=(10, 0))
        self.strategy_buttons = {}
        for idx, key in enumerate(('smart_ru', 'game_only', 'global')):
            btn = tk.Button(strat_wrap, text=STRATEGIES[key], bd=0, relief='flat', cursor='hand2', font=('Segoe UI Semibold', 9), command=lambda k=key: self._set_strategy(k), padx=14, pady=6)
            btn.grid(row=0, column=idx, padx=2, pady=2)
            self.strategy_buttons[key] = btn

        theme_wrap = tk.Frame(action_row, bg=p['segment'], highlightbackground=p['border'], highlightthickness=1)
        theme_wrap.pack(side='right')
        self.theme_buttons = {}
        for idx, key in enumerate(('system', 'light', 'dark')):
            btn = tk.Button(theme_wrap, text=THEME_LABELS[key], bd=0, relief='flat', cursor='hand2', font=('Segoe UI Semibold', 8), command=lambda k=key: self._set_theme_mode(k), padx=10, pady=6)
            btn.grid(row=0, column=idx, padx=2, pady=2)
            self.theme_buttons[key] = btn
        self._refresh_theme_buttons()
        self._refresh_strategy_buttons()
        self._bind_strategy_shortcuts(strat_wrap)

        # Сворачиваемая панель расширенных настроек
        self.advanced = tk.Frame(toolbar, bg=p['card'])
        self.advanced.grid_columnconfigure(1, weight=1)
        self.advanced.grid_columnconfigure(3, weight=1)
        tk.Label(self.advanced, text='sing-box.exe', bg=p['card'], fg=p['text'], font=('Segoe UI Semibold', 9)).grid(row=0, column=0, sticky='w', padx=(0, 8), pady=(2, 3))
        tk.Entry(self.advanced, textvariable=self.singbox_var, bg=p['card2'], fg=p['text'], insertbackground=p['text'], relief='flat', font=('Consolas', 9), bd=0).grid(row=1, column=0, columnspan=2, sticky='ew', padx=(0, 8), ipady=5)
        tk.Button(self.advanced, text='Обзор', command=self._browse_singbox, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=5).grid(row=1, column=2, padx=(0, 12))
        tk.Label(self.advanced, text='xray.exe', bg=p['card'], fg=p['text'], font=('Segoe UI Semibold', 9)).grid(row=0, column=3, sticky='w', padx=(0, 8), pady=(2, 3))
        tk.Entry(self.advanced, textvariable=self.xray_var, bg=p['card2'], fg=p['text'], insertbackground=p['text'], relief='flat', font=('Consolas', 9), bd=0).grid(row=1, column=3, columnspan=2, sticky='ew', padx=(0, 8), ipady=5)
        tk.Button(self.advanced, text='Обзор', command=self._browse_xray, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=5).grid(row=1, column=5)
        tk.Button(self.advanced, text='Обновить списки', command=self._manual_update_lists, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=5).grid(row=2, column=0, pady=(10, 0), sticky='w')
        tk.Button(self.advanced, text='Установить / обновить ядра', command=lambda: self._install_cores(manual=True), bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=5).grid(row=2, column=1, pady=(10, 0), sticky='w', padx=(8,0))
        tk.Label(self.advanced, textvariable=self.block_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9)).grid(row=2, column=2, columnspan=4, sticky='w', pady=(10, 0), padx=(8,0))
        tk.Button(self.advanced, text='Приложения VPN', command=self.open_app_manager, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=5).grid(row=3, column=0, pady=(10, 0), sticky='w')
        tk.Label(self.advanced, textvariable=self.custom_apps_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9)).grid(row=3, column=1, columnspan=3, sticky='w', pady=(10, 0), padx=(8,0))
        tk.Checkbutton(self.advanced, text='Автопереподключение', variable=self.auto_reconnect_var, command=self._save_settings, bg=p['card'], fg=p['text'], activebackground=p['card'], activeforeground=p['text'], selectcolor=p['card2'], bd=0).grid(row=3, column=4, columnspan=2, sticky='e', pady=(10, 0))
        if self.advanced_open:
            self.advanced.pack(fill='x', padx=10, pady=(0, 10))

        tk.Button(action_row, text='Расширенные', command=self._toggle_advanced, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=7).pack(side='right', padx=(8, 0))

        # Основная область
        paned = tk.PanedWindow(outer, bg=p['root'], bd=0, sashrelief='flat', sashwidth=6)
        paned.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        upper = tk.Frame(paned, bg=p['card'], highlightbackground=p['border'], highlightthickness=1)
        lower = tk.Frame(paned, bg=p['card'], highlightbackground=p['border'], highlightthickness=1)
        paned.add(upper, minsize=260)
        paned.add(lower, minsize=140)

        # Верхняя часть: список узлов и статус
        head = tk.Frame(upper, bg=p['card'])
        head.pack(fill='x', padx=10, pady=(8, 6))

        title_row = tk.Frame(head, bg=p['card'])
        title_row.pack(fill='x')
        tk.Label(title_row, text='Серверы', bg=p['card'], fg=p['text'], font=('Segoe UI Semibold', 10)).pack(side='left')

        cards = tk.Frame(head, bg=p['card'])
        cards.pack(fill='x', pady=(8, 6))
        self._make_summary_card(cards, 'Узел', self.node_info_var)
        self._make_summary_card(cards, 'Маршрут', self.route_info_var)
        self._make_summary_card(cards, 'Стратегия', self.strategy_info_var)
        self._make_summary_card(cards, 'Состояние', self.state_info_var)

        tk.Label(head, textvariable=self.status_var, bg=p['card'], fg=p['muted'], font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(0, 2))
        self._refresh_header_summary()

        tf = ttk.Frame(upper, style='Card.TFrame')
        tf.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        cols = ('name', 'type', 'ping', 'udp', 'status')
        self.tree = ttk.Treeview(tf, columns=cols, show='headings', selectmode='browse')
        for c, title, width in (
            ('name', 'Псевдоним', 360),
            ('type', 'Протокол', 270),
            ('ping', 'Задержка', 100),
            ('udp', 'UDP', 70),
            ('status', 'Статус', 180),
        ):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor='w' if c in {'name', 'type', 'status'} else 'center')
        sbv = ttk.Scrollbar(tf, orient='vertical', command=self.tree.yview, style='Vertical.TScrollbar')
        self.tree.configure(yscrollcommand=sbv.set)
        self.tree.pack(side='left', fill='both', expand=True)
        sbv.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self._on_preview_node)
        self.tree.bind('<Double-Button-1>', self._on_double_click_node, add='+')
        self.tree.bind('<Button-3>', self._show_node_menu, add='+')
        self.tree.tag_configure('chosen', background=p['good_bg'])
        self.tree.tag_configure('bad', foreground=p['bad'])

        # Нижняя часть: журнал
        lhead = tk.Frame(lower, bg=p['card'])
        lhead.pack(fill='x', padx=10, pady=(8, 6))
        tk.Label(lhead, text='Журнал', bg=p['card'], fg=p['text'], font=('Segoe UI Semibold', 10)).pack(side='left')
        tk.Label(lhead, textvariable=self.admin_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9)).pack(side='right')
        self.logbox = tk.Text(lower, bg=p['menu_bg'], fg=p['text'], insertbackground=p['text'], relief='flat', bd=0, font=('Consolas', 10), wrap='word', height=8)
        self.logbox.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.logbox.configure(state='disabled')

        # Нижняя строка состояния
        bottom = tk.Frame(outer, bg=p['card'], highlightbackground=p['border'], highlightthickness=1)
        bottom.pack(fill='x', padx=12, pady=(0, 10))
        self.bottom_left = tk.Label(bottom, text='TUN: system · MTU 1400', bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9), padx=10, pady=7)
        self.bottom_left.pack(side='left')
        self.bottom_center = tk.Label(bottom, textvariable=self.engine_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9), padx=10, pady=7)
        self.bottom_center.pack(side='left')
        self.bottom_ru = tk.Label(bottom, text='RU / SU / РФ: DIRECT', bg=p['card'], fg=p['good'], font=('Segoe UI Semibold', 9), padx=10, pady=7)
        self.bottom_ru.pack(side='left')
        self.version_label = tk.Label(bottom, text=f'v{APP_VERSION}', bg=p['card'], fg=p['muted'], font=('Segoe UI', 9), padx=10, pady=7)
        self.version_label.pack(side='right')
        self.bottom_right = tk.Label(bottom, text='Стратегия: —', bg=p['card'], fg=p['text'], font=('Segoe UI', 9, 'bold'), padx=10, pady=7)
        self.bottom_right.pack(side='right')










    def _make_summary_card(self, parent, title: str, variable: tk.StringVar):
        p = self.palette
        box = tk.Frame(parent, bg=p['card2'], highlightbackground=p['border'], highlightthickness=1)
        box.pack(side='left', fill='x', expand=True, padx=(0, 8))
        tk.Label(box, text=title, bg=p['card2'], fg=p['muted'], font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=10, pady=(7, 1))
        tk.Label(box, textvariable=variable, bg=p['card2'], fg=p['text'], font=('Segoe UI', 10), anchor='w').pack(fill='x', padx=10, pady=(0, 8))
        return box

    def _refresh_header_summary(self):
        active_node = self.applied_node if (self.runner and self.runner.running() and self.applied_node) else self.selected_node
        if active_node:
            ping = f'{active_node.https_ms:.0f} ms' if active_node.https_ms is not None else 'FAIL'
            udp = 'UDP OK' if active_node.udp_ok else 'UDP OFF'
            self.node_info_var.set(active_node.name)
            self.route_info_var.set(f'{active_node.stack_label()} · {ping} · {udp}')
            self.engine_var.set(f'Ядро: {active_node.engine_label()}')
        else:
            self.node_info_var.set('—')
            self.route_info_var.set('—')
            self.engine_var.set('Ядро: —')

        strategy_key = self.applied_strategy_key if (self.runner and self.runner.running() and self.applied_strategy_key) else self.strategy_key_var.get()
        self.strategy_info_var.set(STRATEGIES.get(strategy_key, '—'))

        if self.runner and self.runner.running():
            self.state_info_var.set('VPN запущен')
        elif self.busy:
            self.state_info_var.set('Проверка узлов')
        elif self.selected_node:
            self.state_info_var.set('Готово к запуску')
        else:
            self.state_info_var.set('Ожидание')

    def _append_log(self, text: str):
        if not hasattr(self, 'logbox'):
            return
        self.logbox.configure(state='normal')
        self.logbox.insert('end', text.rstrip() + '\n')
        self.logbox.see('end')
        self.logbox.configure(state='disabled')

    def _rebuild_ui(self):
        for child in self.winfo_children():
            child.destroy()
        self._style()
        self._build()
        self._refresh_tree()
        self._refresh_strategy_buttons()
        self._refresh_theme_buttons()
        self._refresh_header_summary()
        if self.runner and self.runner.running():
            self.start_btn.configure(state='disabled')
            self.apply_btn.configure(state='normal')
            self.stop_btn.configure(state='normal')
        elif self.selected_node:
            self.start_btn.configure(state='normal')
        self.after(50, self._sync_titlebar_theme)

    # ---------------- Стратегия ----------------
    def _strategy_menu_label(self, key: str) -> str:
        running = bool(self.runner and self.runner.running())
        if running and self.applied_strategy_key == key:
            return f'✓ {STRATEGIES[key]} — применена'
        if self.strategy_key_var.get() == key:
            return f'• {STRATEGIES[key]} — выбрана'
        return STRATEGIES[key]

    def _show_strategy_menu(self, event=None):
        p = self.palette
        menu = tk.Menu(self, tearoff=0, bg=p['menu_bg'], fg=p['text'], activebackground=p['menu_active'], activeforeground=p['accent_text'], bd=0, relief='flat', font=('Segoe UI', 10))
        for key in ('smart_ru', 'game_only', 'global'):
            menu.add_command(label=self._strategy_menu_label(key), command=lambda k=key: self._choose_strategy_from_menu(k))
        try:
            if event is not None:
                x, y = event.x_root, event.y_root
            else:
                x, y = self.winfo_pointerx(), self.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return 'break'

    def _choose_strategy_from_menu(self, key: str):
        self._set_strategy(key)
        if self.runner and self.runner.running():
            self.after(80, self.apply_strategy)

    def _double_click_strategy(self, key: str):
        self._set_strategy(key)
        if self.runner and self.runner.running():
            self.status_var.set(f'Переключаю стратегию на {STRATEGIES[key]}...')
            self.after(80, self.apply_strategy)
        return 'break'

    def _bind_strategy_shortcuts(self, strategy_area):
        strategy_area.bind('<Button-3>', self._show_strategy_menu, add='+')
        for key, btn in self.strategy_buttons.items():
            btn.bind('<Button-3>', self._show_strategy_menu, add='+')
            btn.bind('<Double-Button-1>', lambda _event, k=key: self._double_click_strategy(k), add='+')

    def _set_strategy(self, key: str):
        if key not in STRATEGIES:
            return
        self.strategy_key_var.set(key)
        self._refresh_strategy_buttons()
        self._save_settings()
        self.bottom_right.config(text=f'Стратегия: {STRATEGIES[key]}')
        self._append_log(f'[STRATEGY] Выбрана стратегия: {STRATEGIES[key]}')
        self._refresh_header_summary()
        if self.runner and self.runner.running():
            self.status_var.set('Стратегия выбрана. Нажми «Применить стратегию».')
            self.apply_btn.configure(state='normal')

    def _refresh_strategy_buttons(self):
        if not hasattr(self, 'strategy_buttons'):
            return
        p = self.palette
        selected = self.strategy_key_var.get()
        running = bool(self.runner and self.runner.running())
        applied = self.applied_strategy_key if running else None
        for key, btn in self.strategy_buttons.items():
            if applied == key:
                btn.configure(bg=p['good'], fg='#FFFFFF', activebackground=p['good'], activeforeground='#FFFFFF')
            elif selected == key:
                btn.configure(bg=p['accent'], fg=p['accent_text'], activebackground=p['accent_hover'], activeforeground=p['accent_text'])
            else:
                btn.configure(bg=p['segment'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'])

    def _toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced.pack(fill='x', padx=10, pady=(0, 10))
        else:
            self.advanced.pack_forget()

    # ---------------- Приложения и watchdog ----------------
    def _refresh_custom_apps_label(self):
        if not hasattr(self, 'custom_apps_var'):
            return
        if self.custom_vpn_processes:
            preview = ', '.join(self.custom_vpn_processes[:3])
            if len(self.custom_vpn_processes) > 3:
                preview += f' +{len(self.custom_vpn_processes) - 3}'
            self.custom_apps_var.set(f'Приложения VPN: {preview}')
        else:
            self.custom_apps_var.set('Приложения VPN: не выбраны')

    def open_app_manager(self):
        p = self.palette
        window = tk.Toplevel(self)
        window.title('Приложения через VPN')
        window.geometry('560x420')
        window.minsize(500, 360)
        window.configure(bg=p['root'])
        window.transient(self)

        tk.Label(window, text='Эти EXE будут идти через VPN в режимах Smart и «Приложения».', bg=p['root'], fg=p['text'], font=('Segoe UI', 10)).pack(anchor='w', padx=14, pady=(14, 8))
        frame = tk.Frame(window, bg=p['card'], highlightbackground=p['border'], highlightthickness=1)
        frame.pack(fill='both', expand=True, padx=14, pady=(0, 10))
        listbox = tk.Listbox(frame, bg=p['card'], fg=p['text'], selectbackground=p['selection'], relief='flat', bd=0, font=('Segoe UI', 10))
        listbox.pack(fill='both', expand=True, padx=8, pady=8)
        self.app_listbox = listbox
        self._refresh_app_listbox()

        buttons = tk.Frame(window, bg=p['root'])
        buttons.pack(fill='x', padx=14, pady=(0, 14))
        tk.Button(buttons, text='Добавить EXE', command=self._add_vpn_app, bg=p['accent'], fg=p['accent_text'], activebackground=p['accent_hover'], activeforeground=p['accent_text'], relief='flat', bd=0, padx=12, pady=6).pack(side='left')
        tk.Button(buttons, text='Удалить', command=self._remove_vpn_app, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=6).pack(side='left', padx=(8, 0))
        tk.Button(buttons, text='Закрыть', command=window.destroy, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=6).pack(side='right')

    def _refresh_app_listbox(self):
        listbox = getattr(self, 'app_listbox', None)
        if not listbox or not listbox.winfo_exists():
            return
        listbox.delete(0, 'end')
        for name in self.custom_vpn_processes:
            listbox.insert('end', name)

    def _add_vpn_app(self):
        path = filedialog.askopenfilename(title='Выберите приложение', filetypes=[('Windows EXE', '*.exe')])
        if not path:
            return
        name = Path(path).name
        self.custom_vpn_processes = normalize_process_names(self.custom_vpn_processes + [name])
        self._save_settings()
        self._refresh_custom_apps_label()
        self._refresh_app_listbox()
        self._append_log(f'[ROUTE] Добавлено приложение через VPN: {name}')

    def _remove_vpn_app(self):
        listbox = getattr(self, 'app_listbox', None)
        if not listbox or not listbox.winfo_exists():
            return
        selection = listbox.curselection()
        if not selection:
            return
        name = str(listbox.get(selection[0]))
        self.custom_vpn_processes = [item for item in self.custom_vpn_processes if item.lower() != name.lower()]
        self._save_settings()
        self._refresh_custom_apps_label()
        self._refresh_app_listbox()
        self._append_log(f'[ROUTE] Удалено приложение из VPN: {name}')

    def _poll_runner_health(self):
        runner = self.runner
        if runner and not runner.running():
            reason = runner.failure_reason()
            self.runner = None
            self.applied_strategy_key = None
            self.applied_node = None
            self.start_btn.configure(state='normal' if self.selected_node else 'disabled')
            self.apply_btn.configure(state='disabled')
            self.stop_btn.configure(state='disabled')
            self.status_var.set('VPN неожиданно остановлен')
            self._append_log('[WATCHDOG] VPN-процесс завершился неожиданно')
            if reason:
                self._append_log('[WATCHDOG] ' + reason.replace('\n', ' | '))
            self._refresh_header_summary()

            if self.auto_reconnect_var.get() and self.selected_node and not self._auto_reconnect_attempted:
                self._auto_reconnect_attempted = True
                self.status_var.set('VPN остановлен. Пробую переподключиться...')
                self._append_log('[WATCHDOG] Автоматическое переподключение через 2 секунды')
                self.after(2000, self.start_vpn)

        self.after(1500, self._poll_runner_health)

    # ---------------- Настройки ----------------
    def _load_settings(self):
        data = load_settings(SETTINGS_PATH)
        self.subscriptions, self.active_subscription_id = load_subscriptions(data)
        self._load_active_subscription_vars()

        self.singbox_var.set(str(data.get('singbox_path') or ''))
        self.xray_var.set(str(data.get('xray_path') or ''))

        strategy = str(data.get('route_strategy') or 'smart_ru')
        self.strategy_key_var.set(strategy if strategy in STRATEGIES else 'smart_ru')

        theme = str(data.get('theme_mode') or 'system')
        self.theme_mode_var.set(theme if theme in THEME_LABELS else 'system')

        self.custom_vpn_processes = normalize_process_names(data.get('custom_vpn_processes') or [])
        self.auto_reconnect_var.set(bool(data.get('auto_reconnect', True)))
        self._refresh_custom_apps_label()

    def _save_settings(self):
        self._store_active_subscription_from_vars()
        data = {
            'subscriptions': dump_subscriptions(self.subscriptions),
            'active_subscription_id': self.active_subscription_id,
            'singbox_path': self.singbox_var.get().strip(),
            'xray_path': self.xray_var.get().strip(),
            'route_strategy': self.strategy_key_var.get(),
            'theme_mode': self.theme_mode_var.get(),
            'custom_vpn_processes': list(self.custom_vpn_processes),
            'auto_reconnect': bool(self.auto_reconnect_var.get()),
            'test_limit': 48,
        }
        try:
            save_settings(SETTINGS_PATH, data)
        except Exception as exc:
            if hasattr(self, 'logbox'):
                self._append_log(f'[SETTINGS] Ошибка сохранения: {exc}')

    # ---------------- Буфер обмена ----------------
    def _clipboard_win32(self) -> str:
        if os.name != 'nt':
            return ''
        CF_UNICODETEXT = 13
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        if not u.OpenClipboard(None):
            return ''
        try:
            h = u.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ''
            ptr = k.GlobalLock(h)
            if not ptr:
                return ''
            try:
                return ctypes.wstring_at(ptr)
            finally:
                k.GlobalUnlock(h)
        finally:
            u.CloseClipboard()

    def _paste(self, _event=None):
        text = ''
        try:
            text = str(self.clipboard_get())
        except Exception:
            try:
                text = self._clipboard_win32()
            except Exception:
                pass
        if text.strip():
            self.url_var.set(text.strip())
            self._save_settings()
            self.status_var.set('Подписка вставлена и сохранена')
            self._refresh_header_summary()
            self._append_log('[SUB] Подписка вставлена и сохранена')
        return 'break'

    def _bind_paste(self, entry: tk.Entry):
        for seq in ('<Control-v>', '<Control-V>', '<Shift-Insert>'):
            entry.bind(seq, self._paste, add='+')
        def hard(event):
            ctrl = bool(int(getattr(event, 'state', 0) or 0) & 0x0004)
            if os.name == 'nt':
                try:
                    ctrl = ctrl or bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
                except Exception:
                    pass
            if ctrl and int(getattr(event, 'keycode', 0) or 0) == 0x56:
                return self._paste(event)
            return None
        entry.bind('<KeyPress>', hard, add='+')
        entry.bind('<FocusOut>', lambda _e: self._save_settings(), add='+')

    # ---------------- Первый запуск и ядра ----------------
    def _first_run_core_check(self):
        self._auto_find_cores()
        missing = []
        if not self.singbox:
            missing.append("sing-box")
        if not self.xray:
            missing.append("Xray")

        if not missing:
            self._append_log("[CORE] Ядра найдены, установка не требуется")
            return

        names = " и ".join(missing)
        answer = messagebox.askyesno(
            "Первый запуск ProstoKVN Network",
            f"Не найдены: {names}.\n\n"
            "Для работы без установленного v2rayN ProstoKVN Network может самостоятельно "
            "скачать официальные Windows-релизы sing-box (SagerNet) и Xray-core (XTLS) "
            "с GitHub и хранить их в профиле пользователя.\n\n"
            "Установить необходимые компоненты сейчас?",
        )
        if answer:
            self._install_cores(manual=False)
        else:
            self.status_var.set("Ядра не установлены — можно установить через «Расширенные»")
            self._refresh_header_summary()
            self._append_log("[CORE] Автоматическая установка отклонена пользователем")

    def _install_cores(self, manual: bool = True):
        if self.busy:
            return

        self.status_var.set("Устанавливаю официальные VPN-ядра...")
        self._refresh_header_summary()
        self._append_log("[CORE] Начинаю установку с официальных GitHub Releases")

        def progress(text: str):
            self.events.put(("core_progress", text))

        def worker():
            try:
                result = install_official_cores(progress=progress)
                self.events.put(("cores_installed", result))
            except Exception as exc:
                self.events.put(("cores_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Ядра и списки ----------------
    def _auto_find_cores(self):
        try:
            self.singbox = find_singbox_binary(self.singbox_var.get().strip())
            self.singbox_var.set(str(self.singbox))
        except Exception:
            self.singbox = None
        try:
            self.xray = find_xray_binary(self.xray_var.get().strip())
            self.xray_var.set(str(self.xray))
        except Exception:
            self.xray = None
        self._save_settings()

    def _browse_singbox(self):
        pth = filedialog.askopenfilename(title='sing-box.exe', filetypes=[('EXE', '*.exe')])
        if pth:
            self.singbox_var.set(pth)
            self.singbox = Path(pth)
            self._save_settings()

    def _browse_xray(self):
        pth = filedialog.askopenfilename(title='xray.exe', filetypes=[('EXE', '*.exe')])
        if pth:
            self.xray_var.set(pth)
            self.xray = Path(pth)
            self._save_settings()

    def _auto_update_lists(self):
        age = blocklists_age_seconds()
        if age is None or age > 6 * 3600 or not self.blocklist_paths:
            threading.Thread(target=self._update_lists_worker, daemon=True).start()
        else:
            self.block_var.set(f'кэш {len(self.blocklist_paths)} файлов, {age/3600:.1f} ч')

    def _manual_update_lists(self):
        self.block_var.set('обновление...')
        self._append_log('[LIST] Обновляю списки доменов...')
        threading.Thread(target=self._update_lists_worker, daemon=True).start()

    def _update_lists_worker(self):
        try:
            update_ru_blocklists(lambda _x: None)
            self.blocklist_paths = get_cached_ru_blocklists()
            self.events.put(('lists', len(self.blocklist_paths)))
        except Exception as exc:
            self.events.put(('lists_error', str(exc)))

    def _autoload_saved_subscription(self):
        item = self._active_subscription()
        if not item or not item.enabled:
            return
        url = item.url.strip()
        if url.startswith(('http://', 'https://')) and not self.busy and not (self.runner and self.runner.running()):
            self.url_var.set(url)
            self.status_var.set('Автоматически загружаю сохранённую подписку...')
            self._refresh_header_summary()
            self._append_log(f'[SUB] Автоматическая загрузка: {item.name}')
            self.start_test(auto=True)

    # ---------------- События ----------------
    def _drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'row':
                    self._receive_tested_node(payload)
                elif kind == 'done':
                    self._finish(payload)
                elif kind == 'error':
                    self.busy = False
                    self.test_btn.configure(state='normal')
                    self.status_var.set('Ошибка')
                    self._append_log(f'[ERROR] {payload}')
                    messagebox.showerror('ProstoKVN Network', str(payload))
                elif kind == 'started':
                    if isinstance(payload, tuple) and len(payload) == 2:
                        applied_key, applied_node = payload
                    else:
                        applied_key, applied_node = self.strategy_key_var.get(), self.selected_node
                    self.applied_strategy_key = str(applied_key)
                    self._auto_reconnect_attempted = False
                    self.applied_node = applied_node if isinstance(applied_node, Node) else self.selected_node
                    if self.applied_node:
                        self.selected_node = self.applied_node
                    self._mark_chosen_node(self.selected_node)
                    self.start_btn.configure(state='disabled')
                    self.apply_btn.configure(state='normal')
                    self.stop_btn.configure(state='normal')
                    node_name = self.applied_node.name if self.applied_node else '—'
                    self.status_var.set(f'VPN запущен · {STRATEGIES.get(self.applied_strategy_key, self.applied_strategy_key)} · {node_name}')
                    self.bottom_right.config(text=f'Стратегия: {STRATEGIES.get(self.applied_strategy_key, self.applied_strategy_key)}')
                    self._append_log(f'[VPN] Запущен: {node_name} | стратегия {STRATEGIES.get(self.applied_strategy_key, self.applied_strategy_key)}')
                    self._refresh_strategy_buttons()
                    self._refresh_tree()
                    self._refresh_header_summary()
                elif kind == 'stopped':
                    self.applied_strategy_key = None
                    self.applied_node = None
                    self.stop_btn.configure(state='disabled')
                    self.apply_btn.configure(state='disabled')
                    if self.selected_node:
                        self.start_btn.configure(state='normal')
                    self.status_var.set('VPN остановлен')
                    self.bottom_right.config(text=f'Стратегия: {STRATEGIES.get(self.strategy_key_var.get(), self.strategy_key_var.get())}')
                    self._append_log('[VPN] Остановлен')
                    self._refresh_strategy_buttons()
                    self._refresh_tree()
                elif kind == 'lists':
                    self.block_var.set(f'готово: {payload} файлов')
                    self._append_log(f'[LIST] Списки обновлены: {payload} файлов')
                elif kind == 'lists_error':
                    self.block_var.set('ошибка обновления; используется кэш')
                    self._append_log(f'[LIST] Ошибка обновления: {payload}')
                elif kind == 'core_progress':
                    self.status_var.set(str(payload))
                    self._append_log(f'[CORE] {payload}')
                    self._refresh_header_summary()
                elif kind == 'cores_installed':
                    result = payload if isinstance(payload, dict) else {}
                    if result.get('singbox'):
                        self.singbox = Path(result['singbox'])
                        self.singbox_var.set(str(self.singbox))
                    if result.get('xray'):
                        self.xray = Path(result['xray'])
                        self.xray_var.set(str(self.xray))
                    self._save_settings()
                    self.status_var.set('Компоненты установлены. ProstoKVN Network готов к работе.')
                    self._append_log('[CORE] sing-box и Xray успешно установлены')
                    self._refresh_header_summary()
                    self.after(250, self._autoload_saved_subscription)
                elif kind == 'cores_error':
                    self.status_var.set('Не удалось установить VPN-ядра')
                    self._append_log(f'[CORE] Ошибка установки: {payload}')
                    messagebox.showerror(
                        'ProstoKVN Network',
                        'Не удалось автоматически установить компоненты:\n\n' + str(payload)
                    )
                elif kind == 'update_none':
                    if payload:
                        self.status_var.set(f'Установлена актуальная версия v{APP_VERSION}')
                        self._append_log('[UPDATE] Обновлений нет')
                elif kind == 'update_error':
                    if isinstance(payload, tuple):
                        manual, error_text = payload
                    else:
                        manual, error_text = False, str(payload)
                    self._append_log(f'[UPDATE] Ошибка проверки: {error_text}')
                    if manual:
                        messagebox.showerror('ProstoKVN Network', 'Не удалось проверить обновления:\n\n' + str(error_text))
                elif kind == 'update_available':
                    self._offer_update(payload)
                elif kind == 'update_downloaded':
                    self._finish_self_update(payload)
                elif kind == 'update_download_error':
                    self.status_var.set('Ошибка загрузки обновления')
                    self._append_log(f'[UPDATE] Ошибка загрузки: {payload}')
                    messagebox.showerror('ProstoKVN Network', 'Не удалось загрузить обновление:\n\n' + str(payload))
        except queue.Empty:
            pass
        self.after(100, self._drain)

    # ---------------- Список узлов ----------------
    def _balanced(self, nodes: list[Node], limit: int = 48) -> list[Node]:
        if len(nodes) <= limit:
            return nodes

        groups: dict[str, list[Node]] = {}
        for node in nodes:
            groups.setdefault(node.protocol, []).append(node)

        result: list[Node] = []
        index = 0
        keys = list(groups)
        while len(result) < limit and keys:
            next_keys: list[str] = []
            for key in keys:
                if index < len(groups[key]) and len(result) < limit:
                    result.append(groups[key][index])
                    next_keys.append(key)
                elif index + 1 < len(groups[key]):
                    next_keys.append(key)
            index += 1
            keys = next_keys
        return result

    def start_test(self, auto: bool = False):
        if self.busy:
            return
        self._save_settings()
        url = self.url_var.get().strip()
        if not url.startswith(('http://', 'https://')):
            if not auto:
                messagebox.showwarning('ProstoKVN Network', 'Вставь ссылку подписки.')
            return
        self._auto_find_cores()
        if not self.singbox:
            if not auto:
                answer = messagebox.askyesno(
                    'ProstoKVN Network',
                    'Не найден sing-box.exe. Установить официальные sing-box и Xray автоматически?'
                )
                if answer:
                    self._install_cores(manual=True)
            else:
                self.status_var.set('Ожидаю установку VPN-ядер...')
            return
        self.stop_vpn(silent=True)
        self.nodes = []
        self.tested_nodes = []
        self.selected_node = None
        self.applied_node = None
        self._refresh_tree()
        self.best_var.set('Узел: —')
        self.busy = True
        self._refresh_header_summary()
        self.test_btn.configure(state='disabled')
        self.start_btn.configure(state='disabled')
        self.apply_btn.configure(state='disabled')
        self.status_var.set('Подписка загружается автоматически...' if auto else 'Проверяю узлы...')
        self._refresh_header_summary()
        self._append_log('[SUB] Проверка узлов начата')
        threading.Thread(target=self._test_worker, args=(url,), daemon=True).start()

    def _test_worker(self, url: str):
        try:
            nodes, _ua = download_subscription(url, lambda _x: None)
            self.nodes = nodes
            subset = self._balanced(nodes, 48)
            tested = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(test_node, node, self.singbox, self.xray, 3.0) for node in subset]
                for future in as_completed(futures):
                    node = future.result()
                    tested.append(node)
                    self.events.put(('row', node))
            self.events.put(('done', tested))
        except Exception as exc:
            self.events.put(('error', str(exc).replace(url, '<subscription>')))

    def _receive_tested_node(self, node: Node):
        existing = None
        for i, n in enumerate(self.tested_nodes):
            if n.name == node.name and n.server == node.server and n.port == node.port:
                existing = i
                break
        if existing is None:
            self.tested_nodes.append(node)
        else:
            self.tested_nodes[existing] = node
        self._refresh_tree()

    def _filtered_nodes(self) -> list[Node]:
        query = self.filter_var.get().strip().lower()
        nodes = self.tested_nodes or []
        if not query:
            return nodes
        out = []
        for n in nodes:
            hay = f'{n.name} {n.stack_label()} {n.protocol} {n.server}'.lower()
            if query in hay:
                out.append(n)
        return out

    def _refresh_tree(self):
        if not hasattr(self, 'tree'):
            return
        p = self.palette
        current_sel = None
        selection = self.tree.selection()
        if selection:
            current_sel = selection[0]
        self.tree.delete(*self.tree.get_children())
        for n in self._filtered_nodes():
            iid = str(id(n))
            ping = f'{n.https_ms:.0f} ms' if n.https_ms is not None else 'FAIL'
            tags = []
            if not n.udp_ok or not n.valid:
                tags.append('bad')
            if self.selected_node is n:
                tags.append('chosen')
            self.tree.insert('', 'end', iid=iid, values=(n.name, n.stack_label(), ping, 'YES' if n.udp_ok else 'NO', n.test_status), tags=tuple(tags))
        self.tree.tag_configure('chosen', background=p['good_bg'])
        self.tree.tag_configure('bad', foreground=p['bad'])
        if self.selected_node:
            iid = str(id(self.selected_node))
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
        elif current_sel and self.tree.exists(current_sel):
            self.tree.selection_set(current_sel)

    def _mark_chosen_node(self, node: Node | None):
        self.selected_node = node
        self._refresh_tree()

    def _node_from_iid(self, iid: str) -> Node | None:
        for node in self.tested_nodes:
            if str(id(node)) == iid:
                return node
        return None

    def _node_under_pointer(self, event):
        iid = self.tree.identify_row(event.y)
        return iid, self._node_from_iid(iid) if iid else None

    def _on_preview_node(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        node = self._node_from_iid(selection[0])
        if not node:
            return
        ping = f'{node.https_ms:.0f} ms' if node.https_ms is not None else 'FAIL'
        if node is self.selected_node:
            self.best_var.set(f'Выбран: {node.name} | {node.stack_label()} | {ping}')
        else:
            self.best_var.set(f'Просмотр: {node.name} | {node.stack_label()} | {ping} · двойной клик или ПКМ для выбора')
        self._refresh_header_summary()

    def _select_node(self, node: Node, apply_now: bool = False):
        self.selected_node = node
        self._mark_chosen_node(node)
        ping = f'{node.https_ms:.0f} ms' if node.https_ms is not None else 'FAIL'
        self.best_var.set(f'Выбран: {node.name} | {node.stack_label()} | {ping}')
        self._append_log(f'[NODE] Выбран узел: {node.name}')
        self._refresh_header_summary()
        if self.runner and self.runner.running():
            if apply_now:
                self.status_var.set(f'Переключаю VPN на {node.name}...')
                self.after(60, self.apply_strategy)
            else:
                self.status_var.set('Выбран другой узел. ПКМ → «Подключить сейчас» или двойной клик для переключения.')
                self.apply_btn.configure(state='normal')
        elif not self.busy:
            self.start_btn.configure(state='normal')
            self.status_var.set('Узел выбран. Можно запускать VPN.')

    def _show_node_menu(self, event):
        iid, node = self._node_under_pointer(event)
        if not iid or not node:
            return 'break'
        self.tree.selection_set(iid)
        p = self.palette
        menu = tk.Menu(self, tearoff=0, bg=p['menu_bg'], fg=p['text'], activebackground=p['menu_active'], activeforeground=p['accent_text'], bd=0, relief='flat', font=('Segoe UI', 10))
        is_chosen = node is self.selected_node
        is_applied = (self.runner and self.runner.running() and node is self.applied_node)
        title = node.name
        if is_applied:
            title = f'✓ {title} — подключён'
        elif is_chosen:
            title = f'• {title} — выбран'
        menu.add_command(label=title, state='disabled')
        menu.add_separator()
        menu.add_command(label='Выбрать узел', command=lambda n=node: self._select_node(n, apply_now=False))
        if self.runner and self.runner.running():
            menu.add_command(label='Подключить сейчас', command=lambda n=node: self._select_node(n, apply_now=True))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return 'break'

    def _on_double_click_node(self, event):
        iid, node = self._node_under_pointer(event)
        if not iid or not node:
            return 'break'
        self._select_node(node, apply_now=bool(self.runner and self.runner.running()))
        return 'break'

    def _finish(self, tested: list[Node]):
        self.busy = False
        self.test_btn.configure(state='normal')
        good = [n for n in tested if n.valid and n.https_ms is not None]
        good.sort(key=lambda n: n.score, reverse=True)
        all_sorted = sorted(tested, key=lambda n: n.score, reverse=True)
        self.tested_nodes = all_sorted
        active_subscription = self._active_subscription()
        if active_subscription:
            touch_subscription(active_subscription)
            self._save_settings()
        best = good[0] if good else (all_sorted[0] if all_sorted else None)
        self.selected_node = best
        self._refresh_tree()
        if best:
            ping = f'{best.https_ms:.0f} ms' if best.https_ms is not None else 'FAIL'
            udp_text = 'OK' if best.udp_ok else 'FAIL'
            self.best_var.set(f'Выбран: {best.name} | {best.stack_label()} | {ping}')
            self.status_var.set(f'Подписка загружена · {len(self.nodes)} узлов')
            self.start_btn.configure(state='normal')
            self._append_log(f'[SUB] Найден лучший узел: {best.name} | {ping} | UDP {udp_text}')
            self._refresh_header_summary()
        else:
            self.status_var.set('Рабочих узлов нет')
            self._append_log('[SUB] Рабочие узлы не найдены')
            self._refresh_header_summary()

    # ---------------- Обновления ----------------
    def check_for_updates(self, manual: bool = False):
        self._append_log("[UPDATE] Проверяю GitHub Releases...")
        if manual:
            self.status_var.set("Проверяю обновления...")

        def worker():
            try:
                info = check_latest_release(APP_VERSION, UPDATE_API, UPDATE_ASSET, UPDATE_HASH_ASSET)
                if info is None:
                    self.events.put(("update_none", manual))
                    return
                info["manual"] = manual
                self.events.put(("update_available", info))
            except Exception as exc:
                self.events.put(("update_error", (manual, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def _offer_update(self, info: dict):
        latest = str(info.get("version") or "?")
        notes = str(info.get("notes") or "").strip()
        short_notes = notes[:700] + ("..." if len(notes) > 700 else "")
        text = f"Доступна новая версия ProstoKVN Network v{latest}.\nТекущая версия: v{APP_VERSION}.\n\n"
        if short_notes:
            text += short_notes + "\n\n"
        text += "Скачать и установить обновление сейчас?"

        if messagebox.askyesno("Обновление ProstoKVN Network", text):
            self._download_update(info)
        else:
            self.status_var.set(f"Доступно обновление v{latest}")
            self._append_log(f"[UPDATE] v{latest} отложено пользователем")

    def _download_update(self, info: dict):
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                "ProstoKVN Network",
                "Автоустановка работает в собранной EXE-версии.\nПри запуске из исходников новая версия только обнаруживается.",
            )
            return

        self.status_var.set(f"Скачиваю ProstoKVN Network v{info.get('version')}...")
        self._append_log(f"[UPDATE] Загрузка v{info.get('version')}")

        def worker():
            try:
                exe_path = download_update(info, APP_VERSION)
                self.events.put(("update_downloaded", {
                    "version": str(info.get("version") or ""),
                    "path": exe_path,
                }))
            except Exception as exc:
                self.events.put(("update_download_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_self_update(self, payload: dict):
        new_exe = Path(payload["path"]).resolve()
        launch_self_updater(new_exe, Path(sys.executable).resolve(), os.getpid())
        self._append_log(f"[UPDATE] Установка v{payload.get('version')} после закрытия программы")
        self.stop_vpn(silent=True)
        self.destroy()

    # ---------------- VPN ----------------
    def _build_runner(self):
        route_mode = self.strategy_key_var.get()
        paths = list(self.blocklist_paths or get_cached_ru_blocklists())
        if route_mode == 'smart_ru' and not paths:
            update_ru_blocklists(lambda _x: None)
            paths[:] = get_cached_ru_blocklists()
        return TunRunner(
            self.singbox,
            self.selected_node,
            discord_vpn=True,
            steam_webhelper_vpn=False,
            xray=self.xray,
            blocked_ru_vpn=(route_mode == 'smart_ru'),
            blocklist_paths=paths,
            route_mode=route_mode,
            custom_vpn_processes=self.custom_vpn_processes,
        )

    def start_vpn(self):
        if not self.selected_node:
            messagebox.showwarning('ProstoKVN Network', 'Сначала дождись загрузки подписки.')
            return
        self._auto_find_cores()
        if not self.singbox:
            messagebox.showerror('ProstoKVN Network', 'Не найден sing-box.exe.')
            return
        self._save_settings()
        self.status_var.set('Запускаю VPN...')
        self.start_btn.configure(state='disabled')
        route_mode = self.strategy_key_var.get()
        node_to_apply = self.selected_node
        self._append_log(f'[VPN] Запуск: {node_to_apply.name if node_to_apply else "—"}')
        self._refresh_header_summary()
        def worker():
            try:
                self.runner = self._build_runner()
                self.runner.start()
                self.events.put(('started', (route_mode, node_to_apply)))
            except Exception as exc:
                self.runner = None
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def apply_strategy(self):
        if not self.selected_node:
            messagebox.showwarning('ProstoKVN Network', 'Сначала дождись загрузки подписки.')
            return
        self._save_settings()
        self.status_var.set(f'Применяю стратегию {STRATEGIES[self.strategy_key_var.get()]}...')
        route_mode = self.strategy_key_var.get()
        node_to_apply = self.selected_node
        self._append_log(f'[VPN] Переключение: {node_to_apply.name if node_to_apply else "—"} | {STRATEGIES[route_mode]}')
        self._refresh_header_summary()
        def worker():
            try:
                if self.runner:
                    self.runner.stop()
                self.runner = self._build_runner()
                self.runner.start()
                self.events.put(('started', (route_mode, node_to_apply)))
            except Exception as exc:
                self.runner = None
                self.applied_strategy_key = None
                self.applied_node = None
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def stop_vpn(self, silent: bool = False):
        self._auto_reconnect_attempted = False
        runner = self.runner
        self.runner = None
        if runner:
            try:
                runner.stop()
            except Exception:
                pass
        if not silent:
            self.events.put(('stopped', None))

    def on_close(self):
        self._save_settings()
        self.stop_vpn(silent=True)
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
