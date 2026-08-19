# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os

try:
    import winreg
except Exception:
    winreg = None

APP_VERSION = "0.21.0"
UPDATE_REPO = "GRESHNIK2019/ProstoKVN-Network"
UPDATE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_ASSET = "ProstoKVNNetwork.exe"
UPDATE_HASH_ASSET = "ProstoKVNNetwork.exe.sha256"

STRATEGIES = {
    "smart_ru": "Smart",
    "game_only": "Games",
    "global": "Global",
}

STRATEGY_DESCRIPTIONS = {
    "smart_ru": "Блокировки РФ + YouTube/Discord/Telegram + игры через VPN",
    "game_only": "Только игры / Ubisoft / Discord через VPN",
    "global": "Почти весь трафик через VPN, Steam.exe остаётся DIRECT",
}

THEME_LABELS = {
    "system": "Система",
    "light": "Светлая",
    "dark": "Тёмная",
}

PALETTES = {
    "dark": {
        "root": "#18191C", "card": "#1F2024", "card2": "#25272C", "border": "#34363C",
        "text": "#F2F2F2", "secondary": "#B5BAC1", "muted": "#8B8F97", "accent": "#2A8CFF",
        "accent_hover": "#4A9EFF", "accent_text": "#FFFFFF", "segment": "#2B2D33",
        "segment_hover": "#373A42", "good_bg": "#0E4B2D", "good": "#39D16D",
        "bad": "#FF5E57", "selection": "#234A75", "menu_bg": "#141519", "menu_active": "#2A8CFF",
    },
    "light": {
        "root": "#F3F5F7", "card": "#FFFFFF", "card2": "#F1F3F5", "border": "#D8DDE3",
        "text": "#111111", "secondary": "#4B5563", "muted": "#6B7280", "accent": "#1677FF",
        "accent_hover": "#3A8CFF", "accent_text": "#FFFFFF", "segment": "#ECEFF3",
        "segment_hover": "#E3E8EF", "good_bg": "#DDF6E5", "good": "#118A43",
        "bad": "#D22D20", "selection": "#D9E8FF", "menu_bg": "#FFFFFF", "menu_active": "#1677FF",
    },
}


def detect_windows_theme() -> str:
    if os.name != "nt" or winreg is None:
        return "dark"
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except Exception:
        return "dark"
