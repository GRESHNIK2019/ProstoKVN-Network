# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from nodes import Node

PROTECTED_DIRECT = [
    "sing-box.exe",
    "sing-box-client.exe",
    "xray.exe",
    "v2ray.exe",
    "python.exe",
    "pythonw.exe",
    "ProstoKVNNetwork.exe",
]
STEAM_DIRECT = ["steam.exe", "GameOverlayUI.exe"]
DISCORD_PROCESSES = ["Discord.exe"]
TELEGRAM_PROCESSES = ["Telegram.exe"]

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
    "ubisoft.com",
    "ubi.com",
    "ubisoftconnect.com",
    "uplay.com",
]
RU_DIRECT_DOMAIN_SUFFIXES = [".ru", ".su", ".рф", ".xn--p1ai"]


def normalize_process_names(values: object) -> list[str]:
    if isinstance(values, str):
        source = values.replace(";", ",").split(",")
    elif isinstance(values, (list, tuple, set)):
        source = list(values)
    else:
        source = []

    result: list[str] = []
    seen: set[str] = set()
    for value in source:
        name = str(value or "").strip().replace("/", "\\").rsplit("\\", 1)[-1]
        if not name:
            continue
        if not name.lower().endswith(".exe"):
            name += ".exe"
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def is_reserved_direct_process(value: str) -> bool:
    names = normalize_process_names([value])
    if not names:
        return False
    reserved = {name.lower() for name in PROTECTED_DIRECT + STEAM_DIRECT}
    return names[0].lower() in reserved


def _rule_sets_for_paths(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    definitions: list[dict[str, Any]] = []
    tags: list[str] = []

    for index, path in enumerate(paths):
        if not path.exists():
            continue
        tag = f"ru_block_{index}"
        file_format = "binary" if path.suffix.lower() == ".srs" else "source"
        definitions.append({
            "type": "local",
            "tag": tag,
            "format": file_format,
            "path": str(path),
        })
        tags.append(tag)

    return definitions, tags


def build_route_rules(
    route_mode: str,
    custom_vpn_processes: list[str] | None = None,
    discord_vpn: bool = True,
    steam_webhelper_vpn: bool = False,
    blocked_ru_vpn: bool = True,
    blocklist_paths: list[Path] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    rules: list[dict[str, Any]] = [
        {"network": ["tcp", "udp"], "port": [53], "action": "hijack-dns"},
        {"action": "sniff"},
        {"process_name": PROTECTED_DIRECT, "action": "route", "outbound": "direct"},
        {"process_name": STEAM_DIRECT, "action": "route", "outbound": "direct"},
    ]

    # Российские домены имеют приоритет над правилами приложений.
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

    rule_definitions: list[dict[str, Any]] = []
    if route_mode == "smart_ru" and blocked_ru_vpn and blocklist_paths:
        rule_definitions, tags = _rule_sets_for_paths(blocklist_paths)
        if tags:
            rules.append({"rule_set": tags, "action": "route", "outbound": "proxy"})

    final_outbound = "proxy" if route_mode == "global" else "direct"
    return rules, rule_definitions, final_outbound


def make_tun_config(
    node: Node,
    log_path: Path,
    discord_vpn: bool = True,
    steam_webhelper_vpn: bool = False,
    blocked_ru_vpn: bool = True,
    blocklist_paths: list[Path] | None = None,
    proxy_override: dict[str, Any] | None = None,
    route_mode: str = "smart_ru",
    custom_vpn_processes: list[str] | None = None,
) -> dict[str, Any]:
    outbound = copy.deepcopy(proxy_override if proxy_override is not None else node.outbound)
    outbound["tag"] = "proxy"

    rules, rule_definitions, final_outbound = build_route_rules(
        route_mode=route_mode,
        custom_vpn_processes=custom_vpn_processes,
        discord_vpn=discord_vpn,
        steam_webhelper_vpn=steam_webhelper_vpn,
        blocked_ru_vpn=blocked_ru_vpn,
        blocklist_paths=blocklist_paths,
    )

    route: dict[str, Any] = {
        "auto_detect_interface": True,
        "rules": rules,
        "final": final_outbound,
    }
    if rule_definitions:
        route["rule_set"] = rule_definitions

    return {
        "log": {"level": "warn", "timestamp": True, "output": str(log_path)},
        "dns": {
            "servers": [{"type": "local", "tag": "local-dns"}],
            "final": "local-dns",
            "strategy": "prefer_ipv4",
            "reverse_mapping": True,
            "cache_capacity": 4096,
        },
        "inbounds": [{
            "type": "tun",
            "tag": "prostokvn-tun",
            "interface_name": "prostokvn_network_tun",
            "address": ["172.29.77.1/30"],
            "mtu": 1400,
            "auto_route": True,
            "strict_route": False,
            "stack": "system",
        }],
        "outbounds": [outbound, {"type": "direct", "tag": "direct"}],
        "route": route,
        "experimental": {
            "clash_api": {
                "external_controller": "127.0.0.1:19181",
                "secret": "",
            }
        },
    }
