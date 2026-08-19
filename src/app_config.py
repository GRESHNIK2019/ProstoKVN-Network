# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os

try:
    import winreg
except Exception:
    winreg = None

APP_VERSION = "0.22.0"
UPDATE_REPO = "GRESHNIK2019/ProstoKVN-Network"
UPDATE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_ASSET = "ProstoKVNNetwork.exe"
UPDATE_HASH_ASSET = "ProstoKVNNetwork.exe.sha256"

STRATEGIES = {
    "smart_ru": "Smart",
    "game_only": "Приложения",
    "global": "Global",
}

STRATEGY_DESCRIPTIONS = {
    "smart_ru": "Блокируемые сервисы + выбранные приложения через VPN, российские сайты напрямую",
    "game_only": "Только выбранные приложения и Discord через VPN",
    "global": "Почти весь трафик через VPN, Steam и российские домены остаются DIRECT",
}

THEME_LABELS = {
    "system": "Система",
    "light": "Светлая",
    "dark": "Тёмная",
}

PALETTES = {
    "dark": {
        "root": "#07111F",
        "card": "#0B1727",
        "card2": "#102039",
        "toolbar": "#0A1B30",
        "hero": "#081B30",
        "footer": "#081728",
        "field": "#0A1A2C",
        "table_head": "#0E2036",
        "log_bg": "#071421",
        "border": "#1D3A58",
        "accent_border": "#1F82D8",
        "text": "#F3F8FF",
        "secondary": "#B6C6D9",
        "muted": "#7E94AC",
        "accent": "#168DF8",
        "accent_hover": "#29A4FF",
        "accent_text": "#FFFFFF",
        "cyan": "#22C8FF",
        "cyan_dim": "#145B7C",
        "segment": "#10233B",
        "segment_hover": "#173251",
        "nav_active": "#0D2845",
        "good_bg": "#0C392B",
        "good": "#55E875",
        "bad": "#FF5D61",
        "danger_bg": "#321923",
        "selection": "#123D68",
        "selected_row": "#103D68",
        "menu_bg": "#06111D",
        "menu_active": "#168DF8",
    },
    "light": {
        "root": "#EDF3F9",
        "card": "#FFFFFF",
        "card2": "#F2F7FC",
        "toolbar": "#F7FAFD",
        "hero": "#F6FBFF",
        "footer": "#F8FBFE",
        "field": "#F4F8FC",
        "table_head": "#EEF5FB",
        "log_bg": "#F7FAFD",
        "border": "#CAD8E5",
        "accent_border": "#7EBBF1",
        "text": "#122033",
        "secondary": "#4E6278",
        "muted": "#73869A",
        "accent": "#1677E8",
        "accent_hover": "#2689FA",
        "accent_text": "#FFFFFF",
        "cyan": "#0097C9",
        "cyan_dim": "#A9DDF0",
        "segment": "#E8F0F7",
        "segment_hover": "#DCE9F4",
        "nav_active": "#DDEEFF",
        "good_bg": "#DDF6E5",
        "good": "#148A46",
        "bad": "#D73C3C",
        "danger_bg": "#FCE7E7",
        "selection": "#D6EAFE",
        "selected_row": "#D7EBFF",
        "menu_bg": "#FFFFFF",
        "menu_active": "#1677E8",
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
