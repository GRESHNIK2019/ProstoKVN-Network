# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import APP_VERSION, STRATEGIES


FONT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"


def _button(
    parent,
    text: str,
    command,
    palette: dict[str, str],
    *,
    primary: bool = False,
    danger: bool = False,
    width: int | None = None,
    state: str = "normal",
    padx: int = 15,
    pady: int = 8,
):
    if primary:
        bg = palette["accent"]
        fg = palette["accent_text"]
        active_bg = palette["accent_hover"]
    elif danger:
        bg = palette.get("danger_bg", palette["card2"])
        fg = palette["bad"]
        active_bg = palette["segment_hover"]
    else:
        bg = palette["card2"]
        fg = palette["text"]
        active_bg = palette["segment_hover"]

    kwargs = {
        "text": text,
        "command": command,
        "bg": bg,
        "fg": fg,
        "activebackground": active_bg,
        "activeforeground": fg,
        "disabledforeground": palette["muted"],
        "relief": "flat",
        "bd": 0,
        "cursor": "hand2",
        "font": (FONT_SEMIBOLD, 9),
        "padx": padx,
        "pady": pady,
        "state": state,
        "highlightthickness": 1,
        "highlightbackground": palette.get("accent_border", palette["border"]) if primary else palette["border"],
        "highlightcolor": palette.get("accent_border", palette["border"]) if primary else palette["border"],
    }
    if width is not None:
        kwargs["width"] = width
    return tk.Button(parent, **kwargs)


def _nav_item(parent, icon: str, text: str, palette: dict[str, str], command=None, active: bool = False):
    wrap = tk.Frame(parent, bg=palette.get("nav_active", palette["card2"]) if active else palette["root"])
    wrap.pack(side="left", fill="y")
    label = tk.Label(
        wrap,
        text=f"{icon}  {text}",
        bg=wrap["bg"],
        fg=palette["text"] if active else palette["secondary"],
        font=(FONT_SEMIBOLD if active else FONT, 10),
        padx=18,
        pady=12,
        cursor="hand2" if command else "arrow",
    )
    label.pack(fill="both", expand=True)
    if active:
        line = tk.Frame(wrap, bg=palette.get("cyan", palette["accent"]), height=2)
        line.pack(fill="x", side="bottom")
    if command:
        label.bind("<Button-1>", lambda _event: command())
        wrap.bind("<Button-1>", lambda _event: command())
    return wrap


def _panel(parent, palette: dict[str, str], *, bg_key: str = "card", padx: int = 0, pady: int = 0):
    return tk.Frame(
        parent,
        bg=palette.get(bg_key, palette["card"]),
        highlightbackground=palette["border"],
        highlightthickness=1,
        padx=padx,
        pady=pady,
    )


def _metric(parent, palette: dict[str, str], icon: str, value, caption: str, accent: str | None = None):
    item = tk.Frame(parent, bg=parent["bg"])
    item.pack(side="left", fill="x", expand=True, padx=(0, 16))
    top = tk.Frame(item, bg=parent["bg"])
    top.pack(anchor="w")
    tk.Label(
        top,
        text=icon,
        bg=parent["bg"],
        fg=accent or palette.get("cyan", palette["accent"]),
        font=(FONT_SEMIBOLD, 14),
    ).pack(side="left", padx=(0, 8))
    tk.Label(
        top,
        textvariable=value if isinstance(value, tk.Variable) else None,
        text="" if isinstance(value, tk.Variable) else str(value),
        bg=parent["bg"],
        fg=palette["text"],
        font=(FONT_SEMIBOLD, 10),
        anchor="w",
    ).pack(side="left")
    tk.Label(
        item,
        text=caption,
        bg=parent["bg"],
        fg=palette["muted"],
        font=(FONT, 8),
        anchor="w",
    ).pack(anchor="w", padx=(30, 0), pady=(2, 0))
    return item


def _draw_shield(canvas: tk.Canvas, palette: dict[str, str], running: bool = False) -> None:
    canvas.delete("all")
    accent = palette.get("cyan", palette["accent"])
    glow = palette.get("cyan_dim", palette["selection"])
    good = palette["good"] if running else accent
    canvas.create_oval(9, 9, 121, 121, outline=glow, width=7)
    canvas.create_oval(17, 17, 113, 113, outline=accent, width=2)
    shield = [65, 34, 91, 44, 88, 76, 65, 96, 42, 76, 39, 44]
    canvas.create_polygon(shield, outline=accent, fill=palette.get("hero", palette["card"]), width=3)
    canvas.create_line(53, 65, 62, 74, 79, 56, fill=good, width=4, capstyle="round", joinstyle="round")


def _capture_log(app) -> str:
    box = getattr(app, "logbox", None)
    if box is None:
        return ""
    try:
        if not box.winfo_exists():
            return ""
        return box.get("1.0", "end-1c")
    except Exception:
        return ""


def _clear_log(app) -> None:
    box = getattr(app, "logbox", None)
    if box is None:
        return
    try:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.configure(state="disabled")
    except Exception:
        pass


def _focus_filter(app) -> None:
    try:
        app.filter_entry.focus_set()
        app.filter_entry.selection_range(0, "end")
    except Exception:
        pass


def _configure_tree(app, frame, palette: dict[str, str]) -> None:
    cols = ("name", "type", "ping", "udp", "status")
    app.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
    columns = (
        ("name", "Узел", 355, "w"),
        ("type", "Движок / протокол", 285, "w"),
        ("ping", "Задержка", 105, "center"),
        ("udp", "UDP", 72, "center"),
        ("status", "Статус", 120, "center"),
    )
    for key, title, width, anchor in columns:
        app.tree.heading(key, text=title)
        app.tree.column(key, width=width, anchor=anchor, stretch=key in {"name", "type"})

    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=app.tree.yview, style="Vertical.TScrollbar")
    app.tree.configure(yscrollcommand=scrollbar.set)
    app.tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    app.tree.bind("<<TreeviewSelect>>", app._on_preview_node)
    app.tree.bind("<Double-Button-1>", app._on_double_click_node, add="+")
    app.tree.bind("<Button-3>", app._show_node_menu, add="+")
    app.tree.tag_configure("chosen", background=palette.get("selected_row", palette["selection"]))
    app.tree.tag_configure("bad", foreground=palette["bad"])


def build_dashboard(app) -> None:
    if not app.winfo_exists() or getattr(app, "_modern_dashboard_built", False):
        return

    old_log = _capture_log(app)
    app._modern_dashboard_built = True
    app._dashboard_generation = int(getattr(app, "_dashboard_generation", 0)) + 1
    generation = app._dashboard_generation
    p = app.palette

    for child in list(app.winfo_children()):
        try:
            child.destroy()
        except Exception:
            pass

    try:
        app.geometry("1380x840")
        app.minsize(1120, 690)
    except Exception:
        pass

    app.strategy_buttons = {}
    app.theme_buttons = {}
    app.advanced = tk.Frame(app, bg=p["root"])
    app.advanced_open = False

    outer = tk.Frame(app, bg=p["root"])
    outer.pack(fill="both", expand=True)

    # Верхняя навигация.
    nav = tk.Frame(outer, bg=p["root"], highlightbackground=p["border"], highlightthickness=0)
    nav.pack(fill="x", padx=12, pady=(8, 0))
    _nav_item(nav, "▤", "Серверы", p, active=True)
    _nav_item(nav, "♙", "Группа подписки", p, command=app.open_subscription_manager)
    _nav_item(nav, "⚙", "Настройки", p, command=lambda: app.open_settings("routing"))
    _nav_item(nav, "?", "Помощь", p, command=lambda: app.check_for_updates(manual=True))

    # Подписка.
    sub = _panel(outer, p, bg_key="card")
    sub.pack(fill="x", padx=12, pady=(0, 8))
    left_sub = tk.Frame(sub, bg=p["card"])
    left_sub.pack(side="left", fill="x", expand=True, padx=12, pady=10)
    tk.Label(
        left_sub,
        text="Группа подписки",
        bg=p["card"],
        fg=p["text"],
        font=(FONT_SEMIBOLD, 9),
    ).pack(side="left", padx=(0, 12))
    app.subscription_info = tk.Label(
        left_sub,
        text=app._subscription_info_text(),
        anchor="w",
        bg=p.get("field", p["card2"]),
        fg=p["text"],
        font=(FONT, 10),
        padx=14,
        pady=8,
    )
    app.subscription_info.pack(side="left", fill="x", expand=True)

    sub_actions = tk.Frame(sub, bg=p["card"])
    sub_actions.pack(side="right", padx=10, pady=9)
    _button(sub_actions, "☷  Управлять", app.open_subscription_manager, p).pack(side="left", padx=(0, 8))
    _button(sub_actions, "↻  Обновить подписку", app.start_test, p).pack(side="left")

    # Основные действия.
    actions = _panel(outer, p, bg_key="toolbar")
    actions.pack(fill="x", padx=12, pady=(0, 8))
    row = tk.Frame(actions, bg=actions["bg"])
    row.pack(fill="x", padx=10, pady=9)
    app.test_btn = _button(row, "↻  Обновить узлы", app.start_test, p, primary=True)
    app.test_btn.pack(side="left")
    app.start_btn = _button(row, "▷  Запустить VPN", app.start_vpn, p, state="disabled")
    app.start_btn.pack(side="left", padx=(8, 0))
    app.stop_btn = _button(row, "■  Остановить", app.stop_vpn, p, danger=True, state="disabled")
    app.stop_btn.pack(side="left", padx=(8, 0))

    # Скрытая кнопка нужна старой внутренней логике переключения стратегии.
    app.apply_btn = _button(row, "Применить стратегию", app.apply_strategy, p, state="disabled")

    _button(row, "▽  Фильтр", lambda: _focus_filter(app), p).pack(side="left", padx=(8, 0))
    search_wrap = tk.Frame(
        row,
        bg=p.get("field", p["card2"]),
        highlightbackground=p["border"],
        highlightthickness=1,
    )
    search_wrap.pack(side="left", fill="x", expand=True, padx=(8, 0))
    tk.Label(
        search_wrap,
        text="⌕",
        bg=search_wrap["bg"],
        fg=p["muted"],
        font=(FONT, 12),
        padx=9,
    ).pack(side="left")
    app.filter_entry = tk.Entry(
        search_wrap,
        textvariable=app.filter_var,
        bg=search_wrap["bg"],
        fg=p["text"],
        insertbackground=p["text"],
        relief="flat",
        bd=0,
        font=(FONT, 10),
    )
    app.filter_entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))

    # Большая карточка состояния подключения.
    hero = _panel(outer, p, bg_key="hero")
    hero.pack(fill="x", padx=12, pady=(0, 8))
    hero_bg = hero["bg"]
    shield = tk.Canvas(hero, width=132, height=132, bg=hero_bg, highlightthickness=0, bd=0)
    shield.pack(side="left", padx=(24, 18), pady=12)
    _draw_shield(shield, p, bool(app.runner and app.runner.running()))

    hero_info = tk.Frame(hero, bg=hero_bg)
    hero_info.pack(side="left", fill="both", expand=True, padx=(0, 18), pady=16)
    state_line = tk.Frame(hero_info, bg=hero_bg)
    state_line.pack(fill="x")
    app._hero_state_dot = tk.Label(
        state_line,
        text="●",
        bg=hero_bg,
        fg=p["good"] if app.runner and app.runner.running() else p["muted"],
        font=(FONT, 10),
    )
    app._hero_state_dot.pack(side="left", padx=(0, 7))
    app._hero_state_label = tk.Label(
        state_line,
        textvariable=app.state_info_var,
        bg=hero_bg,
        fg=p["good"] if app.runner and app.runner.running() else p["secondary"],
        font=(FONT_SEMIBOLD, 10),
    )
    app._hero_state_label.pack(side="left")

    tk.Label(
        hero_info,
        textvariable=app.node_info_var,
        bg=hero_bg,
        fg=p["text"],
        font=(FONT_SEMIBOLD, 14),
        anchor="w",
    ).pack(fill="x", pady=(7, 12))

    metric_row = tk.Frame(hero_info, bg=hero_bg)
    metric_row.pack(fill="x")
    _metric(metric_row, p, "◴", app.route_info_var, "Маршрут · задержка · UDP")
    _metric(metric_row, p, "▣", app.engine_var, "Движок")
    _metric(metric_row, p, "◎", app.strategy_info_var, "Стратегия", accent=p["good"])

    app._hero_status_line = tk.Label(
        hero_info,
        textvariable=app.status_var,
        bg=hero_bg,
        fg=p["muted"],
        font=(FONT, 9),
        anchor="w",
    )
    app._hero_status_line.pack(fill="x", pady=(13, 0))

    # Список узлов + журнал.
    split = tk.PanedWindow(
        outer,
        orient="horizontal",
        bg=p["root"],
        bd=0,
        sashwidth=8,
        sashrelief="flat",
        showhandle=False,
    )
    split.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    servers = _panel(split, p, bg_key="card")
    logs = _panel(split, p, bg_key="card")
    split.add(servers, minsize=650, stretch="always")
    split.add(logs, minsize=300, stretch="always")

    shead = tk.Frame(servers, bg=p["card"])
    shead.pack(fill="x", padx=12, pady=(10, 8))
    tk.Label(
        shead,
        text="Список узлов",
        bg=p["card"],
        fg=p["text"],
        font=(FONT_SEMIBOLD, 10),
    ).pack(side="left")
    tk.Label(
        shead,
        text="двойной клик — подключить",
        bg=p["card"],
        fg=p["muted"],
        font=(FONT, 8),
    ).pack(side="right")

    tree_wrap = tk.Frame(servers, bg=p["card"])
    tree_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    _configure_tree(app, tree_wrap, p)

    lhead = tk.Frame(logs, bg=p["card"])
    lhead.pack(fill="x", padx=12, pady=(10, 8))
    tk.Label(
        lhead,
        text="Журнал",
        bg=p["card"],
        fg=p["text"],
        font=(FONT_SEMIBOLD, 10),
    ).pack(side="left")
    tk.Button(
        lhead,
        text="Очистить",
        command=lambda: _clear_log(app),
        bg=p["card"],
        fg=p["muted"],
        activebackground=p["card2"],
        activeforeground=p["text"],
        relief="flat",
        bd=0,
        cursor="hand2",
        font=(FONT, 8),
    ).pack(side="right")
    tk.Label(
        lhead,
        textvariable=app.admin_var,
        bg=p["card"],
        fg=p["secondary"],
        font=(FONT, 8),
    ).pack(side="right", padx=(0, 10))

    log_wrap = tk.Frame(logs, bg=p.get("log_bg", p["menu_bg"]))
    log_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    app.logbox = tk.Text(
        log_wrap,
        bg=p.get("log_bg", p["menu_bg"]),
        fg=p["text"],
        insertbackground=p["text"],
        relief="flat",
        bd=0,
        font=("Consolas", 9),
        wrap="word",
        padx=8,
        pady=8,
        spacing1=1,
        spacing3=2,
    )
    log_scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=app.logbox.yview, style="Vertical.TScrollbar")
    app.logbox.configure(yscrollcommand=log_scroll.set)
    app.logbox.pack(side="left", fill="both", expand=True)
    log_scroll.pack(side="right", fill="y")
    if old_log:
        app.logbox.insert("end", old_log + ("\n" if not old_log.endswith("\n") else ""))
        app.logbox.see("end")
    app.logbox.configure(state="disabled")

    # Нижняя статусная строка.
    footer = _panel(outer, p, bg_key="footer")
    footer.pack(fill="x", padx=12, pady=(0, 10))
    footer_bg = footer["bg"]
    app.bottom_left = tk.Label(
        footer,
        text="◈  TUN: system   •   MTU 1400",
        bg=footer_bg,
        fg=p["secondary"],
        font=(FONT, 9),
        padx=12,
        pady=8,
    )
    app.bottom_left.pack(side="left")
    app.bottom_center = tk.Label(
        footer,
        textvariable=app.engine_var,
        bg=footer_bg,
        fg=p["secondary"],
        font=(FONT, 9),
        padx=12,
        pady=8,
    )
    app.bottom_center.pack(side="left")
    app.bottom_ru = tk.Label(
        footer,
        text="⌘  RU / SU / РФ: DIRECT",
        bg=footer_bg,
        fg=p["good"],
        font=(FONT_SEMIBOLD, 9),
        padx=12,
        pady=8,
    )
    app.bottom_ru.pack(side="left")
    app.version_label = tk.Label(
        footer,
        text=f"v{APP_VERSION}",
        bg=footer_bg,
        fg=p["muted"],
        font=(FONT, 9),
        padx=12,
        pady=8,
    )
    app.version_label.pack(side="right")
    app.bottom_right = tk.Label(
        footer,
        text=f"Стратегия: {STRATEGIES.get(app.strategy_key_var.get(), '—')}",
        bg=footer_bg,
        fg=p["text"],
        font=(FONT_SEMIBOLD, 9),
        padx=12,
        pady=8,
    )
    app.bottom_right.pack(side="right")

    # Обновляем данные после перестройки виджетов.
    try:
        app._refresh_subscription_info()
        app._refresh_tree()
        app._refresh_header_summary()
    except Exception:
        pass

    running = bool(app.runner and app.runner.running())
    if running:
        app.start_btn.configure(state="disabled")
        app.stop_btn.configure(state="normal")
        app.apply_btn.configure(state="normal")
    elif app.selected_node:
        app.start_btn.configure(state="normal")
        app.stop_btn.configure(state="disabled")
        app.apply_btn.configure(state="disabled")

    def refresh_visual_state() -> None:
        if getattr(app, "_dashboard_generation", None) != generation:
            return
        try:
            if not app._hero_state_label.winfo_exists():
                return
            is_running = bool(app.runner and app.runner.running())
            app._hero_state_dot.configure(fg=p["good"] if is_running else p["muted"])
            app._hero_state_label.configure(fg=p["good"] if is_running else p["secondary"])
            _draw_shield(shield, p, is_running)
        except Exception:
            return
        app.after(900, refresh_visual_state)

    app.after(250, refresh_visual_state)
