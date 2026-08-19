# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Совместимый фасад для старых импортов ProstoKVN Network.

Новая логика разделена по небольшим модулям. Этот файл оставлен, чтобы старые
внутренние импорты и сторонние скрипты не ломались после обновления.
"""
from __future__ import annotations

from blocklists import blocklists_age_seconds, get_cached_ru_blocklists, update_ru_blocklists
from cores import find_singbox_binary, find_xray_binary, install_official_cores
from node_tester import protocol_summary, test_node
from nodes import Node, download_subscription
from paths import SETTINGS_PATH
from routing import make_tun_config, normalize_process_names
from vpn_runner import TunRunner, is_admin

__all__ = [
    "Node",
    "TunRunner",
    "SETTINGS_PATH",
    "blocklists_age_seconds",
    "download_subscription",
    "find_singbox_binary",
    "find_xray_binary",
    "get_cached_ru_blocklists",
    "install_official_cores",
    "is_admin",
    "make_tun_config",
    "normalize_process_names",
    "protocol_summary",
    "test_node",
    "update_ru_blocklists",
]
