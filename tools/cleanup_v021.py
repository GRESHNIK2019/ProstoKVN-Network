# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "src" / "core.py"
GUI_PATH = ROOT / "src" / "ProstoKVNNetwork.pyw"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return text.replace(old, new, 1)


def clean_core(text: str) -> str:
    old_imports = '''import base64
import copy
import ctypes
import ipaddress
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import re
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import platform
import shutil
import zipfile
import hashlib
from typing import Any, Callable

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

from paths import (
    APP_DIR, RUNTIME_DIR, USER_DATA_DIR, BLOCKLIST_DIR, SETTINGS_PATH,
    MANAGED_CORE_DIR, BLOCKLIST_META_PATH,
)
'''
    new_imports = '''import copy
import ctypes
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from app_config import APP_VERSION
from nodes import Node, _bool, _split_csv
from paths import BLOCKLIST_DIR, BLOCKLIST_META_PATH, RUNTIME_DIR
'''
    text = replace_once(text, old_imports, new_imports, "core imports")

    text = replace_once(
        text,
        '''\n\nfrom nodes import Node, download_subscription, _bool, _split_csv\n\ndef find_free_port() -> int:\n    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n    s.bind(("127.0.0.1", 0)); port = int(s.getsockname()[1]); s.close(); return port\n\n\n\nfrom cores import install_official_cores, find_singbox_binary, find_xray_binary\n''',
        '''\n\ndef find_free_port() -> int:\n    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:\n        sock.bind(("127.0.0.1", 0))\n        return int(sock.getsockname()[1])\n''',
        "core free port",
    )

    old_node_query = '''def _node_query(node: Node) -> dict[str, str]:
    q = node.extra.get("query")
    if isinstance(q, dict): return {str(k): str(v) for k, v in q.items()}
    if node.source.lower().startswith("vless://"):
        p = urllib.parse.urlsplit(node.source)
        qq = urllib.parse.parse_qs(p.query, keep_blank_values=True)
        return {k: (v[0] if v else "") for k, v in qq.items()}
    clash = node.extra.get("clash")
    if isinstance(clash, dict):
        d: dict[str, str] = {}
        for k, v in clash.items():
            if isinstance(v, (str, int, float, bool)): d[str(k)] = str(v)
        return d
    return {}
'''
    new_node_query = '''def _node_query(node: Node) -> dict[str, str]:
    query = node.extra.get("query")
    if isinstance(query, dict):
        return {str(key): str(value) for key, value in query.items()}

    if node.source.lower().startswith("vless://"):
        parsed = urllib.parse.urlsplit(node.source)
        values = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        return {key: (items[0] if items else "") for key, items in values.items()}

    clash = node.extra.get("clash")
    if isinstance(clash, dict):
        result: dict[str, str] = {}
        for key, value in clash.items():
            if isinstance(value, (str, int, float, bool)):
                result[str(key)] = str(value)
        return result

    return {}
'''
    text = replace_once(text, old_node_query, new_node_query, "core node query")

    text = replace_once(
        text,
        '    out = copy.deepcopy(node.outbound); out["tag"] = "proxy"\n',
        '    out = copy.deepcopy(node.outbound)\n    out["tag"] = "proxy"\n',
        "core test config",
    )

    old_wait = '''def _wait_port(port: int, proc: subprocess.Popen[Any], timeout: float = 4.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None: return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15): return True
        except OSError:
            time.sleep(0.08)
    return False
'''
    new_wait = '''def _wait_port(port: int, proc: subprocess.Popen[Any], timeout: float = 4.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                return True
        except OSError:
            time.sleep(0.08)
    return False
'''
    text = replace_once(text, old_wait, new_wait, "core wait port")

    text = replace_once(
        text,
        '        if not chunk: raise OSError("socket closed")\n',
        '        if not chunk:\n            raise OSError("socket closed")\n',
        "core recv exact",
    )

    text = replace_once(
        text,
        '                    "User-Agent": "ProstoKVNNetwork/0.20",\n',
        '                    "User-Agent": f"ProstoKVNNetwork/{APP_VERSION}",\n',
        "core user agent",
    )

    text = text.replace(
        '# UDP is essential for this game; then reward real endpoint reachability and latency.\n',
        '# UDP имеет высокий вес, затем учитываем доступность TCP-точек и задержку.\n',
    )

    text = replace_once(
        text,
        '''        e, s, r, k = _normalize_domain_list(text)
        exact.update(e); suffix.update(s); regexes.update(r); keywords.update(k)
''',
        '''        current_exact, current_suffix, current_regexes, current_keywords = _normalize_domain_list(text)
        exact.update(current_exact)
        suffix.update(current_suffix)
        regexes.update(current_regexes)
        keywords.update(current_keywords)
''',
        "core domain ruleset",
    )

    text = replace_once(
        text,
        '''    def emit(msg: str) -> None:
        if log:
            try: log(msg)
            except Exception: pass
''',
        '''    def emit(message: str) -> None:
        if not log:
            return
        try:
            log(message)
        except Exception:
            pass
''',
        "core blocklist log",
    )

    old_admin = '''def is_admin() -> bool:
    if os.name != "nt": return True
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False
'''
    new_admin = '''def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
'''
    text = replace_once(text, old_admin, new_admin, "core admin check")

    old_init = '''        self.singbox = singbox; self.xray = xray; self.node = node
        self.discord_vpn = discord_vpn; self.steam_webhelper_vpn = steam_webhelper_vpn
        self.force_game_vpn = force_game_vpn; self.blocked_ru_vpn = blocked_ru_vpn
        self.route_mode = route_mode; self.discord_mode = discord_mode
'''
    new_init = '''        self.singbox = singbox
        self.xray = xray
        self.node = node
        self.discord_vpn = discord_vpn
        self.steam_webhelper_vpn = steam_webhelper_vpn
        self.force_game_vpn = force_game_vpn
        self.blocked_ru_vpn = blocked_ru_vpn
        self.route_mode = route_mode
        self.discord_mode = discord_mode
'''
    text = replace_once(text, old_init, new_init, "core runner init")

    text = replace_once(
        text,
        '        if self.proc and self.proc.poll() is None: return\n',
        '        if self.proc and self.proc.poll() is None:\n            return\n',
        "core runner start",
    )

    old_summary = '''def protocol_summary(nodes: list[Node]) -> dict[str, int]:
    d: dict[str, int] = {}
    for n in nodes:
        key = n.stack_label()
        d[key] = d.get(key, 0) + 1
    return d
'''
    new_summary = '''def protocol_summary(nodes: list[Node]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for node in nodes:
        key = node.stack_label()
        summary[key] = summary.get(key, 0) + 1
    return summary
'''
    text = replace_once(text, old_summary, new_summary, "core protocol summary")
    return text


def clean_gui(text: str) -> str:
    old_header = '''import ctypes
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import queue
import re
import sys
import threading
import urllib.request
import hashlib
import subprocess
import shutil
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import (
    Node, TunRunner, SETTINGS_PATH, blocklists_age_seconds, download_subscription,
    find_singbox_binary, find_xray_binary, get_cached_ru_blocklists, is_admin,
    test_node, update_ru_blocklists, install_official_cores,
)

APP_DIR = Path(__file__).resolve().parent
from app_config import (
    APP_VERSION, PALETTES, STRATEGIES, STRATEGY_DESCRIPTIONS, THEME_LABELS,
    UPDATE_API, UPDATE_ASSET, UPDATE_HASH_ASSET, detect_windows_theme,
)
from updater import check_latest_release, download_update, launch_self_updater
def relaunch_as_admin() -> bool:
'''
    new_header = '''import ctypes
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
from core import (
    TunRunner, blocklists_age_seconds, get_cached_ru_blocklists, is_admin,
    test_node, update_ru_blocklists,
)
from cores import find_singbox_binary, find_xray_binary, install_official_cores
from nodes import Node, download_subscription
from paths import SETTINGS_PATH
from updater import check_latest_release, download_update, launch_self_updater

APP_DIR = Path(__file__).resolve().parent


def relaunch_as_admin() -> bool:
'''
    text = replace_once(text, old_header, new_header, "gui imports")

    comment_replacements = {
        '# ---------------- Theme ----------------': '# ---------------- Тема ----------------',
        '# ---------------- Layout ----------------': '# ---------------- Интерфейс ----------------',
        '# Top menu imitation': '# Верхнее меню',
        '# Toolbar': '# Панель действий',
        '# Advanced panel collapsible': '# Сворачиваемая панель расширенных настроек',
        '# Split area': '# Основная область',
        '# Upper: nodes table + status lines': '# Верхняя часть: список узлов и статус',
        '# Lower: log panel': '# Нижняя часть: журнал',
        '# Bottom status bar': '# Нижняя строка состояния',
        '# ---------------- Strategy ----------------': '# ---------------- Стратегия ----------------',
        '# ---------------- Settings ----------------': '# ---------------- Настройки ----------------',
        '# ---------------- Clipboard ----------------': '# ---------------- Буфер обмена ----------------',
        '# ---------------- First run / cores ----------------': '# ---------------- Первый запуск и ядра ----------------',
        '# ---------------- Cores and lists ----------------': '# ---------------- Ядра и списки ----------------',
        '# ---------------- Events ----------------': '# ---------------- События ----------------',
        '# ---------------- Node list ----------------': '# ---------------- Список узлов ----------------',
        '# ---------------- Updates ----------------': '# ---------------- Обновления ----------------',
        '# ---------------- VPN ----------------': '# ---------------- VPN ----------------',
    }
    for old, new in comment_replacements.items():
        text = text.replace(old, new)

    text = replace_once(
        text,
        '    def _make_summary_card(self, parent, title: str, variable: tk.StringVar, width: int = 220):\n',
        '    def _make_summary_card(self, parent, title: str, variable: tk.StringVar):\n',
        "gui summary card",
    )

    text = replace_once(
        text,
        '''    def _bind_strategy_shortcuts(self, strategy_area):
        for widget in (strategy_area,):
            widget.bind('<Button-3>', self._show_strategy_menu, add='+')
        for key, btn in self.strategy_buttons.items():
''',
        '''    def _bind_strategy_shortcuts(self, strategy_area):
        strategy_area.bind('<Button-3>', self._show_strategy_menu, add='+')
        for key, btn in self.strategy_buttons.items():
''',
        "gui strategy bindings",
    )

    old_balanced = '''    def _balanced(self, nodes: list[Node], limit: int = 48) -> list[Node]:
        if len(nodes) <= limit:
            return nodes
        groups: dict[str, list[Node]] = {}
        for n in nodes:
            groups.setdefault(n.protocol, []).append(n)
        result, i, keys = [], 0, list(groups)
        while len(result) < limit and keys:
            next_keys = []
            for key in keys:
                if i < len(groups[key]) and len(result) < limit:
                    result.append(groups[key][i])
                    next_keys.append(key)
                elif i + 1 < len(groups[key]):
                    next_keys.append(key)
            i += 1
            keys = next_keys
        return result
'''
    new_balanced = '''    def _balanced(self, nodes: list[Node], limit: int = 48) -> list[Node]:
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
'''
    text = replace_once(text, old_balanced, new_balanced, "gui balanced nodes")

    text = replace_once(
        text,
        '''            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(test_node, n, self.singbox, self.xray, 3.0): n for n in subset}
                for future in as_completed(futures):
''',
        '''            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(test_node, node, self.singbox, self.xray, 3.0) for node in subset]
                for future in as_completed(futures):
''',
        "gui test futures",
    )

    text = replace_once(
        text,
        '''    def _filtered_nodes(self):
''',
        '''    def _filtered_nodes(self) -> list[Node]:
''',
        "gui filtered nodes type",
    )

    text = replace_once(
        text,
        '''    def _clear_node_tags(self):
        pass  # rebuild model-based rendering handles this

''',
        '',
        "gui dead node tags",
    )
    return text


def main() -> None:
    core = CORE_PATH.read_text(encoding="utf-8")
    gui = GUI_PATH.read_text(encoding="utf-8")

    cleaned_core = clean_core(core)
    cleaned_gui = clean_gui(gui)

    compile(cleaned_core, str(CORE_PATH), "exec")
    compile(cleaned_gui, str(GUI_PATH), "exec")

    CORE_PATH.write_text(cleaned_core, encoding="utf-8")
    GUI_PATH.write_text(cleaned_gui, encoding="utf-8")
    print("v0.21 source cleanup: OK")


if __name__ == "__main__":
    main()
