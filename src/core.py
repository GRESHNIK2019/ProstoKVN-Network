# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
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

APP_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = APP_DIR / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)

DATA_ROOT = Path(os.environ.get("LOCALAPPDATA") or APP_DIR)
LEGACY_USER_DATA_DIRS = [
    DATA_ROOT / "SmartVPN",
    DATA_ROOT / ("Motor" + "festVPN_AutoSelector"),
]
USER_DATA_DIR = DATA_ROOT / "ProstoKVN Network"

# Одноразовая миграция настроек со старых имён приложения.
if not USER_DATA_DIR.exists():
    for old_dir in LEGACY_USER_DATA_DIRS:
        if not old_dir.exists():
            continue
        try:
            shutil.copytree(old_dir, USER_DATA_DIR, dirs_exist_ok=True)
            break
        except Exception:
            pass

USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
BLOCKLIST_DIR = USER_DATA_DIR / "blocklists"
BLOCKLIST_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = USER_DATA_DIR / "settings.json"
MANAGED_CORE_DIR = USER_DATA_DIR / "cores"
MANAGED_CORE_DIR.mkdir(parents=True, exist_ok=True)
BLOCKLIST_META_PATH = BLOCKLIST_DIR / "meta.json"

ITDOG_DOMAIN_URLS = [
    "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Russia/inside-raw.lst",
    "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Russia/inside-raw.lst",
]
RUNETFREEDOM_DOMAIN_URLS = [
    "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geosite/release/ru-blocked.txt",
    "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geosite@release/ru-blocked.txt",
]

# Сервисные списки ITDog. Они нужны отдельно от общего Russia/inside: например,
# YouTube использует множество CDN/API-доменов, которые не всегда удобно ловить
# одним общим списком. Эти домены тоже маршрутизируются только через VPN.
ITDOG_SERVICE_SOURCES = {
    "youtube": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/youtube.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/youtube.lst",
    ],
    "discord": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/discord.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/discord.lst",
    ],
    "meta": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/meta.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/meta.lst",
    ],
    "twitter": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/twitter.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/twitter.lst",
    ],
    "tiktok": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/tiktok.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/tiktok.lst",
    ],
    "telegram": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/telegram.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/telegram.lst",
    ],
}

# Минимальный встроенный fallback для YouTube. Даже если GitHub/CDN временно
# недоступны при первом запуске, основные YouTube/CDN домены всё равно пойдут VPN.
YOUTUBE_FALLBACK = """
youtube.com
ytimg.com
yting.com
ggpht.com
googlevideo.com
youtubekids.com
youtu.be
yt.be
youtube-nocookie.com
wide-youtube.l.google.com
ytimg.l.google.com
youtubei.googleapis.com
youtubeembeddedplayer.googleapis.com
youtube-ui.l.google.com
yt-video-upload.l.google.com
jnn-pa.googleapis.com
yt3.googleusercontent.com
"""
RUNETFREEDOM_IP_SOURCES = {
    "ru_blocked_ip": [
        "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/ru-blocked.srs",
        "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/ru-blocked.srs",
    ],
    "ru_blocked_community_ip": [
        "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/ru-blocked-community.srs",
        "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/ru-blocked-community.srs",
    ],
    "re_filter_ip": [
        "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/re-filter.srs",
        "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/re-filter.srs",
    ],
}

TARGET_PROCESSES = [
    "TheCrew" + "Motor" + "fest.exe",
    "TheCrew" + "Motor" + "fest_BE.exe",
    "UbisoftConnect.exe",
    "UbisoftConnectWebCore.exe",
    "UbisoftGameLauncher.exe",
    "UbisoftGameLauncher64.exe",
    "UplayWebCore.exe",
    "UplayService.exe",
    "upc.exe",
    "BEService.exe",
    "BEService_x64.exe",
]
STEAM_PROCESSES = ["steam.exe", "steamwebhelper.exe", "GameOverlayUI.exe"]
PROTECTED_DIRECT = [
    "sing-box.exe", "sing-box-client.exe", "v2rayN.exe", "xray.exe", "v2ray.exe",
    "python.exe", "pythonw.exe", "SmartVPN.exe", "ProstoKVNNetwork.exe",
]
DISCORD_PROCESSES = ["Discord.exe"]
TELEGRAM_PROCESSES = ["Telegram.exe"]

# Российские доменные зоны всегда идут напрямую.
# .рф в реальном TLS/DNS обычно приходит в punycode как xn--p1ai.
RU_DIRECT_DOMAIN_SUFFIXES = [
    ".ru",
    ".su",
    ".рф",
    ".xn--p1ai",
]

GAME_TCP_ENDPOINTS = [
    ("76.223.19.28", 443),
    ("3.33.249.140", 443),
    ("185.131.64.122", 443),
    ("166.117.30.225", 443),
]


def b64decode_loose(text: str) -> bytes:
    text = re.sub(r"\s+", "", text.strip())
    if not text:
        return b""
    pad = "=" * ((4 - len(text) % 4) % 4)
    for fn in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return fn((text + pad).encode("ascii"))
        except Exception:
            pass
    raise ValueError("Некорректный Base64")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _qs_first(q: dict[str, list[str]], *names: str, default: str = "") -> str:
    for name in names:
        vals = q.get(name)
        if vals:
            return vals[0]
    return default


def _split_csv(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,|]", value or "") if x.strip()]


def _tls_from_query(q: dict[str, list[str]], security: str, server_default: str) -> dict[str, Any] | None:
    security = (security or "").lower()
    reality = security == "reality"
    tls_on = security in {"tls", "reality"} or _bool(_qs_first(q, "tls"))
    if not tls_on:
        return None
    tls: dict[str, Any] = {"enabled": True}
    sni = _qs_first(q, "sni", "serverName", "servername", "peer")
    if sni:
        tls["server_name"] = sni
    elif server_default and not _is_ip(server_default):
        tls["server_name"] = server_default
    if _bool(_qs_first(q, "allowInsecure", "insecure", "skip-cert-verify")):
        tls["insecure"] = True
    alpn = _qs_first(q, "alpn")
    if alpn:
        tls["alpn"] = _split_csv(urllib.parse.unquote(alpn))
    fp = _qs_first(q, "fp", "fingerprint", "client-fingerprint")
    if fp and fp.lower() not in {"none", "disable", "disabled"}:
        tls["utls"] = {"enabled": True, "fingerprint": fp}
    if reality:
        pub = _qs_first(q, "pbk", "publicKey", "public_key")
        sid = _qs_first(q, "sid", "shortId", "short_id")
        if pub:
            tls["reality"] = {"enabled": True, "public_key": pub, "short_id": sid}
    return tls


def _transport_from_query(q: dict[str, list[str]], kind: str | None = None) -> dict[str, Any] | None:
    t = (kind or _qs_first(q, "type", "network", "net") or "").lower()
    if t in {"", "tcp", "raw", "none"}:
        return None
    host = urllib.parse.unquote(_qs_first(q, "host", "Host", "authority"))
    path = urllib.parse.unquote(_qs_first(q, "path"))
    if t in {"ws", "websocket"}:
        tr: dict[str, Any] = {"type": "ws"}
        if path:
            tr["path"] = path
        if host:
            tr["headers"] = {"Host": host}
        return tr
    if t in {"grpc", "gun"}:
        svc = urllib.parse.unquote(_qs_first(q, "serviceName", "service_name", "service-name"))
        tr = {"type": "grpc"}
        if svc:
            tr["service_name"] = svc
        return tr
    if t in {"httpupgrade", "http-upgrade"}:
        tr = {"type": "httpupgrade"}
        if host:
            tr["host"] = host
        if path:
            tr["path"] = path
        return tr
    if t in {"http", "h2"}:
        tr = {"type": "http"}
        if host:
            tr["host"] = _split_csv(host)
        if path:
            tr["path"] = path
        return tr
    if t == "quic":
        return {"type": "quic"}
    return None


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except Exception:
        return False


def _node_name(fragment: str, fallback: str) -> str:
    n = urllib.parse.unquote(fragment or "").strip()
    return n or fallback


@dataclass
class Node:
    name: str
    protocol: str
    server: str
    port: int
    outbound: dict[str, Any]
    source: str = ""
    valid: bool = True
    error: str = ""
    tcp_ok: int = 0
    tcp_total: int = 0
    udp_ok: bool = False
    https_ms: float | None = None
    score: float = -999999.0
    test_status: str = "Не проверен"
    extra: dict[str, Any] = field(default_factory=dict)

    def display_server(self) -> str:
        return f"{self.server}:{self.port}"

    def stack_label(self) -> str:
        transport = str(self.extra.get("transport") or "").lower()
        security = str(self.extra.get("security") or "").lower()
        if self.protocol == "hysteria2":
            return "HYSTERIA2"
        if self.protocol == "tuic":
            return "TUIC"
        if self.protocol == "shadowsocks":
            return "SHADOWSOCKS"
        parts = [self.protocol.upper()]
        pretty = {
            "tcp": "RAW", "raw": "RAW", "ws": "WS", "websocket": "WS",
            "grpc": "gRPC", "xhttp": "XHTTP", "httpupgrade": "HTTPUpgrade",
            "http-upgrade": "HTTPUpgrade", "http": "HTTP", "h2": "HTTP/2", "quic": "QUIC",
        }
        if transport and transport not in {"none", "tcp", "raw"}:
            parts.append(pretty.get(transport, transport.upper()))
        if security and security not in {"none", ""}:
            parts.append(security.upper())
        return " + ".join(parts)

    def engine_label(self) -> str:
        return str(self.extra.get("engine") or ("xray" if self.protocol == "vless" else "sing-box"))


SUPPORTED_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2", "tuic"}


def parse_vless(link: str) -> Node:
    p = urllib.parse.urlsplit(link)
    q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    host = p.hostname or ""
    port = p.port or 443
    uuid = urllib.parse.unquote(p.username or "")
    name = _node_name(p.fragment, f"VLESS {host}:{port}")
    out: dict[str, Any] = {"type": "vless", "tag": "proxy", "server": host, "server_port": port, "uuid": uuid}
    flow = _qs_first(q, "flow")
    if flow:
        out["flow"] = flow
    pe = _qs_first(q, "packetEncoding", "packet_encoding")
    if pe:
        out["packet_encoding"] = pe
    sec = (_qs_first(q, "security", default="") or "none").lower()
    transport = (_qs_first(q, "type", "network", "net") or "raw").lower()
    # sing-box не умеет XHTTP, но остальные VLESS-транспорты оставляем совместимыми.
    tls = _tls_from_query(q, sec, host)
    if tls:
        out["tls"] = tls
    if transport != "xhttp":
        tr = _transport_from_query(q, transport)
        if tr:
            out["transport"] = tr
    qflat = {k: (v[0] if v else "") for k, v in q.items()}
    extra = {"transport": transport, "security": sec, "engine": "xray", "query": qflat}
    return Node(name, "vless", host, port, out, source=link, extra=extra)

def parse_trojan(link: str) -> Node:
    p = urllib.parse.urlsplit(link)
    q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    host = p.hostname or ""
    port = p.port or 443
    password = urllib.parse.unquote(p.username or "")
    name = _node_name(p.fragment, f"Trojan {host}:{port}")
    out: dict[str, Any] = {"type": "trojan", "tag": "proxy", "server": host, "server_port": port, "password": password}
    sec = _qs_first(q, "security", default="tls")
    tls = _tls_from_query(q, sec, host)
    if tls:
        out["tls"] = tls
    tr = _transport_from_query(q)
    if tr:
        out["transport"] = tr
    return Node(name, "trojan", host, port, out, source=link, extra={"transport": (_qs_first(q, "type", "network", "net") or "raw").lower(), "security": sec or "tls", "engine": "sing-box"})


def parse_hy2(link: str) -> Node:
    p = urllib.parse.urlsplit(link)
    q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    host = p.hostname or ""
    port = p.port or 443
    password = urllib.parse.unquote(p.username or "")
    if p.password:
        password = urllib.parse.unquote((p.username or "") + ":" + p.password)
    name = _node_name(p.fragment, f"Hysteria2 {host}:{port}")
    out: dict[str, Any] = {"type": "hysteria2", "tag": "proxy", "server": host, "server_port": port, "password": password}
    tls: dict[str, Any] = {"enabled": True}
    sni = _qs_first(q, "sni", "peer")
    if sni:
        tls["server_name"] = sni
    elif host and not _is_ip(host):
        tls["server_name"] = host
    if _bool(_qs_first(q, "insecure", "allowInsecure")):
        tls["insecure"] = True
    alpn = _qs_first(q, "alpn")
    if alpn:
        tls["alpn"] = _split_csv(urllib.parse.unquote(alpn))
    out["tls"] = tls
    obfs = _qs_first(q, "obfs")
    obfs_pw = _qs_first(q, "obfs-password", "obfs_password")
    if obfs:
        out["obfs"] = {"type": obfs}
        if obfs_pw:
            out["obfs"]["password"] = obfs_pw
    up = _safe_int(_qs_first(q, "upmbps", "up_mbps"), 0)
    down = _safe_int(_qs_first(q, "downmbps", "down_mbps"), 0)
    if up:
        out["up_mbps"] = up
    if down:
        out["down_mbps"] = down
    return Node(name, "hysteria2", host, port, out, source=link, extra={"transport": "quic", "security": "tls", "engine": "sing-box"})


def parse_tuic(link: str) -> Node:
    p = urllib.parse.urlsplit(link)
    q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    host = p.hostname or ""
    port = p.port or 443
    uuid = urllib.parse.unquote(p.username or "")
    password = urllib.parse.unquote(p.password or "")
    name = _node_name(p.fragment, f"TUIC {host}:{port}")
    out: dict[str, Any] = {
        "type": "tuic", "tag": "proxy", "server": host, "server_port": port,
        "uuid": uuid, "password": password,
    }
    cc = _qs_first(q, "congestion_control", "congestion-control")
    if cc:
        out["congestion_control"] = cc
    mode = _qs_first(q, "udp_relay_mode", "udp-relay-mode")
    if mode:
        out["udp_relay_mode"] = mode
    tls: dict[str, Any] = {"enabled": True}
    sni = _qs_first(q, "sni", "peer")
    if sni:
        tls["server_name"] = sni
    elif host and not _is_ip(host):
        tls["server_name"] = host
    if _bool(_qs_first(q, "insecure", "allowInsecure")):
        tls["insecure"] = True
    alpn = _qs_first(q, "alpn")
    if alpn:
        tls["alpn"] = _split_csv(urllib.parse.unquote(alpn))
    out["tls"] = tls
    return Node(name, "tuic", host, port, out, source=link, extra={"transport": "quic", "security": "tls", "engine": "sing-box"})


def parse_ss(link: str) -> Node:
    raw = link[len("ss://"):]
    frag = ""
    if "#" in raw:
        raw, frag = raw.split("#", 1)
    query = ""
    if "?" in raw:
        raw, query = raw.split("?", 1)
    method = password = host = ""
    port = 0
    if "@" in raw:
        userinfo, addr = raw.rsplit("@", 1)
        try:
            decoded = b64decode_loose(userinfo).decode("utf-8")
        except Exception:
            decoded = urllib.parse.unquote(userinfo)
        if ":" not in decoded:
            raise ValueError("SS: нет method:password")
        method, password = decoded.split(":", 1)
        pp = urllib.parse.urlsplit("ss://x@" + addr)
        host, port = pp.hostname or "", pp.port or 0
    else:
        decoded = b64decode_loose(raw).decode("utf-8")
        if "@" not in decoded:
            raise ValueError("SS: нет @")
        creds, addr = decoded.rsplit("@", 1)
        method, password = creds.split(":", 1)
        pp = urllib.parse.urlsplit("ss://x@" + addr)
        host, port = pp.hostname or "", pp.port or 0
    q = urllib.parse.parse_qs(query, keep_blank_values=True)
    name = _node_name(frag, f"SS {host}:{port}")
    out: dict[str, Any] = {
        "type": "shadowsocks", "tag": "proxy", "server": host, "server_port": port,
        "method": urllib.parse.unquote(method), "password": urllib.parse.unquote(password),
    }
    plugin = _qs_first(q, "plugin")
    if plugin:
        plugin = urllib.parse.unquote(plugin)
        if ";" in plugin:
            pname, popts = plugin.split(";", 1)
            out["plugin"] = pname
            out["plugin_opts"] = popts
        else:
            out["plugin"] = plugin
    return Node(name, "shadowsocks", host, port, out, source=link, extra={"transport": "raw", "security": "shadowsocks", "engine": "sing-box"})


def parse_vmess(link: str) -> Node:
    raw = link[len("vmess://"):].strip()
    obj = json.loads(b64decode_loose(raw).decode("utf-8"))
    host = str(obj.get("add") or obj.get("server") or "")
    port = _safe_int(obj.get("port"), 443)
    name = str(obj.get("ps") or f"VMess {host}:{port}")
    out: dict[str, Any] = {
        "type": "vmess", "tag": "proxy", "server": host, "server_port": port,
        "uuid": str(obj.get("id") or obj.get("uuid") or ""),
        "security": str(obj.get("scy") or obj.get("security") or "auto"),
        "alter_id": _safe_int(obj.get("aid") or obj.get("alterId"), 0),
    }
    tls_name = str(obj.get("tls") or obj.get("security_tls") or "").lower()
    if tls_name in {"tls", "reality"}:
        q: dict[str, list[str]] = {}
        for key, target in (("sni", "sni"), ("fp", "fp"), ("alpn", "alpn")):
            if obj.get(key): q[target] = [str(obj[key])]
        tls = _tls_from_query(q, tls_name, host)
        if tls: out["tls"] = tls
    net = str(obj.get("net") or obj.get("network") or "tcp")
    q = {
        "host": [str(obj.get("host") or "")],
        "path": [str(obj.get("path") or "")],
        "serviceName": [str(obj.get("path") or obj.get("serviceName") or "")],
    }
    tr = _transport_from_query(q, net)
    if tr: out["transport"] = tr
    return Node(name, "vmess", host, port, out, source=link, extra={"transport": net.lower(), "security": tls_name or "none", "engine": "sing-box"})


def parse_share_link(link: str) -> Node:
    s = link.strip()
    low = s.lower()
    if low.startswith("vless://"): return parse_vless(s)
    if low.startswith("vmess://"): return parse_vmess(s)
    if low.startswith("trojan://"): return parse_trojan(s)
    if low.startswith("ss://"): return parse_ss(s)
    if low.startswith("hysteria2://") or low.startswith("hy2://"): return parse_hy2(s)
    if low.startswith("tuic://"): return parse_tuic(s)
    raise ValueError("Неподдерживаемая ссылка")


def _clash_tls(proxy: dict[str, Any], host: str, reality_opts: dict[str, Any] | None = None) -> dict[str, Any] | None:
    tls_on = _bool(proxy.get("tls")) or bool(proxy.get("servername") or proxy.get("sni")) or bool(reality_opts)
    if not tls_on:
        return None
    tls: dict[str, Any] = {"enabled": True}
    sni = str(proxy.get("servername") or proxy.get("sni") or "")
    if sni: tls["server_name"] = sni
    elif host and not _is_ip(host): tls["server_name"] = host
    if _bool(proxy.get("skip-cert-verify")): tls["insecure"] = True
    fp = str(proxy.get("client-fingerprint") or proxy.get("fingerprint") or "")
    if fp: tls["utls"] = {"enabled": True, "fingerprint": fp}
    alpn = proxy.get("alpn")
    if isinstance(alpn, list) and alpn: tls["alpn"] = [str(x) for x in alpn]
    if reality_opts:
        pub = str(reality_opts.get("public-key") or reality_opts.get("public_key") or "")
        sid = str(reality_opts.get("short-id") or reality_opts.get("short_id") or "")
        tls["reality"] = {"enabled": True, "public_key": pub, "short_id": sid}
    return tls


def _clash_transport(proxy: dict[str, Any]) -> dict[str, Any] | None:
    net = str(proxy.get("network") or "").lower()
    if net == "ws":
        opts = proxy.get("ws-opts") or {}
        tr: dict[str, Any] = {"type": "ws"}
        if opts.get("path"): tr["path"] = str(opts["path"])
        headers = opts.get("headers") or {}
        if headers: tr["headers"] = {str(k): str(v) for k, v in headers.items()}
        return tr
    if net == "grpc":
        opts = proxy.get("grpc-opts") or {}
        svc = opts.get("grpc-service-name") or opts.get("service-name") or ""
        tr = {"type": "grpc"}
        if svc: tr["service_name"] = str(svc)
        return tr
    if net in {"http", "h2"}:
        opts = proxy.get("h2-opts") or proxy.get("http-opts") or {}
        tr = {"type": "http"}
        host = opts.get("host") or proxy.get("servername")
        if host: tr["host"] = host if isinstance(host, list) else [str(host)]
        if opts.get("path"): tr["path"] = str(opts["path"])
        return tr
    if net == "httpupgrade":
        opts = proxy.get("http-upgrade-opts") or {}
        tr = {"type": "httpupgrade"}
        if opts.get("host"): tr["host"] = str(opts["host"])
        if opts.get("path"): tr["path"] = str(opts["path"])
        return tr
    return None


def parse_clash_proxy(proxy: dict[str, Any]) -> Node:
    ptype = str(proxy.get("type") or "").lower()
    name = str(proxy.get("name") or ptype or "node")
    host = str(proxy.get("server") or "")
    port = _safe_int(proxy.get("port"), 0)
    net = str(proxy.get("network") or "raw").lower()
    sec = "reality" if isinstance(proxy.get("reality-opts"), dict) else ("tls" if _bool(proxy.get("tls")) else "none")
    extra = {"transport": net, "security": sec, "engine": "xray" if ptype == "vless" else "sing-box", "clash": copy.deepcopy(proxy)}
    out: dict[str, Any]
    if ptype == "vless":
        out = {"type": "vless", "tag": "proxy", "server": host, "server_port": port, "uuid": str(proxy.get("uuid") or "")}
        if proxy.get("flow"): out["flow"] = str(proxy["flow"])
        reality = proxy.get("reality-opts") if isinstance(proxy.get("reality-opts"), dict) else None
        tls = _clash_tls(proxy, host, reality)
        if tls: out["tls"] = tls
        if net != "xhttp":
            tr = _clash_transport(proxy)
            if tr: out["transport"] = tr
        return Node(name, "vless", host, port, out, source="clash", extra=extra)
    if ptype == "vmess":
        out = {"type": "vmess", "tag": "proxy", "server": host, "server_port": port,
               "uuid": str(proxy.get("uuid") or ""), "security": str(proxy.get("cipher") or "auto"),
               "alter_id": _safe_int(proxy.get("alterId"), 0)}
        tls = _clash_tls(proxy, host)
        if tls: out["tls"] = tls
        tr = _clash_transport(proxy)
        if tr: out["transport"] = tr
        return Node(name, "vmess", host, port, out, source="clash", extra=extra)
    if ptype == "trojan":
        out = {"type": "trojan", "tag": "proxy", "server": host, "server_port": port, "password": str(proxy.get("password") or "")}
        tls = _clash_tls({**proxy, "tls": True}, host)
        if tls: out["tls"] = tls
        tr = _clash_transport(proxy)
        if tr: out["transport"] = tr
        return Node(name, "trojan", host, port, out, source="clash", extra=extra)
    if ptype in {"ss", "shadowsocks"}:
        out = {"type": "shadowsocks", "tag": "proxy", "server": host, "server_port": port,
               "method": str(proxy.get("cipher") or proxy.get("method") or ""), "password": str(proxy.get("password") or "")}
        if proxy.get("plugin"):
            out["plugin"] = str(proxy["plugin"])
            opts = proxy.get("plugin-opts") or proxy.get("plugin_opts")
            if isinstance(opts, dict): out["plugin_opts"] = ";".join(f"{k}={v}" for k, v in opts.items())
            elif opts: out["plugin_opts"] = str(opts)
        return Node(name, "shadowsocks", host, port, out, source="clash", extra=extra)
    if ptype in {"hysteria2", "hy2"}:
        out = {"type": "hysteria2", "tag": "proxy", "server": host, "server_port": port,
               "password": str(proxy.get("password") or proxy.get("auth") or "")}
        tls = _clash_tls({**proxy, "tls": True}, host)
        if tls: out["tls"] = tls
        obfs = proxy.get("obfs")
        if obfs:
            out["obfs"] = {"type": str(obfs)}
            if proxy.get("obfs-password"): out["obfs"]["password"] = str(proxy["obfs-password"])
        extra.update({"transport": "quic", "security": "tls", "engine": "sing-box"})
        return Node(name, "hysteria2", host, port, out, source="clash", extra=extra)
    if ptype == "tuic":
        out = {"type": "tuic", "tag": "proxy", "server": host, "server_port": port,
               "uuid": str(proxy.get("uuid") or ""), "password": str(proxy.get("password") or "")}
        if proxy.get("congestion-controller"): out["congestion_control"] = str(proxy["congestion-controller"])
        if proxy.get("udp-relay-mode"): out["udp_relay_mode"] = str(proxy["udp-relay-mode"])
        tls = _clash_tls({**proxy, "tls": True}, host)
        if tls: out["tls"] = tls
        extra.update({"transport": "quic", "security": "tls", "engine": "sing-box"})
        return Node(name, "tuic", host, port, out, source="clash", extra=extra)
    raise ValueError(f"Clash: тип {ptype} пока не поддержан")

def parse_subscription_content(text: str) -> list[Node]:
    candidates: list[Node] = []
    stripped = text.strip().lstrip("\ufeff")

    # sing-box JSON / generic JSON
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            obj = json.loads(stripped)
            outs = obj.get("outbounds") if isinstance(obj, dict) else obj
            if isinstance(outs, list):
                for i, out in enumerate(outs):
                    if not isinstance(out, dict): continue
                    typ = str(out.get("type") or "").lower()
                    if typ not in SUPPORTED_PROTOCOLS: continue
                    o = copy.deepcopy(out)
                    o["tag"] = "proxy"
                    server = str(o.get("server") or "")
                    port = _safe_int(o.get("server_port"), 0)
                    name = str(out.get("tag") or f"{typ} {server}:{port}")
                    candidates.append(Node(name, typ, server, port, o, source="sing-box-json", extra={"transport": str((o.get("transport") or {}).get("type") or "raw") if isinstance(o.get("transport"), dict) else "raw", "security": "tls" if o.get("tls") else "none", "engine": "xray" if typ == "vless" else "sing-box"}))
                if candidates:
                    return dedupe_nodes(candidates)
        except Exception:
            pass

    # Clash YAML
    if yaml is not None and ("proxies:" in stripped[:10000] or stripped.startswith("proxies:")):
        try:
            obj = yaml.safe_load(stripped)
            proxies = obj.get("proxies") if isinstance(obj, dict) else None
            if isinstance(proxies, list):
                for p in proxies:
                    if not isinstance(p, dict): continue
                    try:
                        candidates.append(parse_clash_proxy(p))
                    except Exception:
                        pass
                if candidates:
                    return dedupe_nodes(candidates)
        except Exception:
            pass

    # plain links or base64-encoded list
    variants = [stripped]
    try:
        decoded = b64decode_loose(stripped).decode("utf-8", errors="replace")
        if "://" in decoded:
            variants.insert(0, decoded)
    except Exception:
        pass

    for variant in variants:
        local: list[Node] = []
        for line in variant.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line or "://" not in line:
                continue
            try:
                local.append(parse_share_link(line))
            except Exception:
                continue
        if len(local) > len(candidates):
            candidates = local
    return dedupe_nodes(candidates)


def dedupe_nodes(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    seen: set[str] = set()
    for n in nodes:
        key = json.dumps(n.outbound, sort_keys=True, ensure_ascii=False)
        if key in seen: continue
        seen.add(key); out.append(n)
    return out


def download_subscription(url: str, log: Callable[[str], None] | None = None) -> tuple[list[Node], str]:
    uas = [
        "v2rayN/7.24.4",
        "sing-box/1.13",
        "clash.meta",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    ]
    best: list[Node] = []
    best_ua = ""
    last_err = ""
    for ua in uas:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read(8 * 1024 * 1024)
            text = raw.decode("utf-8", errors="replace")
            nodes = parse_subscription_content(text)
            if log: log(f"Формат подписки через UA '{ua}': найдено узлов {len(nodes)}")
            if len(nodes) > len(best):
                best, best_ua = nodes, ua
        except Exception as exc:
            last_err = type(exc).__name__ + ": " + str(exc)
            if log: log(f"UA '{ua}': не удалось разобрать ответ")
    if not best:
        raise RuntimeError("Подписка загрузилась, но поддерживаемые узлы не найдены. " + (last_err[:200] if last_err else ""))
    return best, best_ua


def find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0)); port = int(s.getsockname()[1]); s.close(); return port



def _windows_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return "amd64"


def _github_latest_release(repo: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _find_release_asset(release: dict[str, Any], matcher: Callable[[str], bool]) -> dict[str, Any]:
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if matcher(name):
            return asset
    raise RuntimeError("В последнем GitHub-релизе не найден подходящий Windows-архив.")


def _download_file(url: str, dest: Path, progress: Callable[[str], None] | None = None) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/1.0",
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress and total > 0:
                pct = int(done * 100 / total)
                progress(f"Загрузка: {pct}%")


def _verify_github_asset_digest(path: Path, asset: dict[str, Any]) -> None:
    """
    GitHub Asset API на новых релизах может возвращать digest=sha256:...
    Если поле есть — обязательно сверяем. Если его нет — файл всё равно скачан
    непосредственно с официального github.com release asset URL.
    """
    digest = str(asset.get("digest") or "").strip().lower()
    if not digest.startswith("sha256:"):
        return
    expected = digest.split(":", 1)[1]
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest().lower() != expected:
        raise RuntimeError("SHA256 загруженного компонента не совпадает с GitHub release asset.")


def _replace_directory(staging: Path, target: Path) -> None:
    old = target.with_name(target.name + ".old")
    try:
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            target.replace(old)
        staging.replace(target)
        shutil.rmtree(old, ignore_errors=True)
    except Exception:
        if not target.exists() and old.exists():
            old.replace(target)
        raise


def install_official_cores(
    progress: Callable[[str], None] | None = None,
    install_singbox: bool = True,
    install_xray: bool = True,
) -> dict[str, Path]:
    """
    Скачивает официальные Windows-релизы непосредственно с GitHub:
      SagerNet/sing-box
      XTLS/Xray-core

    Устанавливает в %LOCALAPPDATA%\ProstoKVN Network\cores.
    """
    def emit(text: str) -> None:
        if progress:
            progress(text)

    arch = _windows_arch()
    result: dict[str, Path] = {}
    MANAGED_CORE_DIR.mkdir(parents=True, exist_ok=True)

    if install_singbox:
        emit("sing-box: получаю информацию о последнем официальном релизе...")
        release = _github_latest_release("SagerNet/sing-box")
        if arch == "arm64":
            matcher = lambda n: n.lower().endswith("-windows-arm64.zip") and n.lower().startswith("sing-box-")
        else:
            matcher = lambda n: n.lower().endswith("-windows-amd64.zip") and n.lower().startswith("sing-box-")
        asset = _find_release_asset(release, matcher)
        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("GitHub не вернул ссылку на sing-box release asset.")

        with tempfile.TemporaryDirectory(prefix="prostokvn-singbox-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            _download_file(url, archive, lambda t: emit(f"sing-box: {t}"))
            _verify_github_asset_digest(archive, asset)

            extracted = td_path / "extract"
            extracted.mkdir()
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extracted)

            exe = next(extracted.rglob("sing-box.exe"), None)
            if exe is None:
                raise RuntimeError("В официальном архиве sing-box не найден sing-box.exe.")

            source_dir = exe.parent
            staging = MANAGED_CORE_DIR / "sing-box.new"
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(source_dir, staging)
            target = MANAGED_CORE_DIR / "sing-box"
            _replace_directory(staging, target)

        result["singbox"] = (MANAGED_CORE_DIR / "sing-box" / "sing-box.exe").resolve()
        emit(f"sing-box: установлен ({release.get('tag_name', 'latest')})")

    if install_xray:
        emit("Xray: получаю информацию о последнем официальном релизе...")
        release = _github_latest_release("XTLS/Xray-core")
        expected = "xray-windows-arm64-v8a.zip" if arch == "arm64" else "xray-windows-64.zip"
        asset = _find_release_asset(release, lambda n: n.lower() == expected)
        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("GitHub не вернул ссылку на Xray release asset.")

        with tempfile.TemporaryDirectory(prefix="prostokvn-xray-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            _download_file(url, archive, lambda t: emit(f"Xray: {t}"))
            _verify_github_asset_digest(archive, asset)

            extracted = td_path / "extract"
            extracted.mkdir()
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extracted)

            exe = next(extracted.rglob("xray.exe"), None)
            if exe is None:
                raise RuntimeError("В официальном архиве Xray не найден xray.exe.")

            source_dir = exe.parent
            staging = MANAGED_CORE_DIR / "xray.new"
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(source_dir, staging)
            target = MANAGED_CORE_DIR / "xray"
            _replace_directory(staging, target)

        result["xray"] = (MANAGED_CORE_DIR / "xray" / "xray.exe").resolve()
        emit(f"Xray: установлен ({release.get('tag_name', 'latest')})")

    return result



def find_singbox_binary(explicit: str = "") -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file(): return p.resolve()
    env = os.environ.get("SINGBOX_EXE")
    if env and Path(env).is_file(): return Path(env).resolve()
    roots = [
        Path(r"C:\Program Files (x86)\v2rayN-windows-64"),
        Path(r"C:\Program Files\v2rayN-windows-64"),
        Path.home() / "Desktop" / "v2rayN-windows-64",
        APP_DIR,
    ]
    names = ["sing-box.exe", "sing-box-client.exe"]
    for root in roots:
        if not root.exists(): continue
        for name in names:
            p = root / "bin" / "sing_box" / name
            if p.is_file(): return p.resolve()
            p = root / name
            if p.is_file(): return p.resolve()
    for root in roots[:2]:
        if not root.exists(): continue
        try:
            for name in names:
                for p in root.glob(f"**/{name}"):
                    if p.is_file(): return p.resolve()
        except Exception:
            pass
    raise FileNotFoundError("Не найден sing-box.exe. ProstoKVN Network может установить официальный core автоматически.")


def find_xray_binary(explicit: str = "") -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file(): return p.resolve()
    env = os.environ.get("XRAY_EXE")
    if env and Path(env).is_file(): return Path(env).resolve()
    managed = MANAGED_CORE_DIR / "xray" / "xray.exe"
    if managed.is_file():
        return managed.resolve()
    roots = [
        Path(r"C:\Program Files (x86)\v2rayN-windows-64"),
        Path(r"C:\Program Files\v2rayN-windows-64"),
        Path.home() / "Desktop" / "v2rayN-windows-64",
        APP_DIR,
    ]
    for root in roots:
        if not root.exists(): continue
        for rel in (Path("bin") / "xray" / "xray.exe", Path("bin") / "Xray" / "xray.exe", Path("xray.exe")):
            p = root / rel
            if p.is_file(): return p.resolve()
    for root in roots[:2]:
        if not root.exists(): continue
        try:
            for p in root.glob("**/xray.exe"):
                if p.is_file(): return p.resolve()
        except Exception:
            pass
    raise FileNotFoundError("Не найден xray.exe. ProstoKVN Network может установить официальный core автоматически.")


def _node_query(node: Node) -> dict[str, str]:
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


def make_xray_vless_outbound(node: Node) -> dict[str, Any]:
    if node.protocol != "vless":
        raise ValueError("Xray builder пока используется только для VLESS")
    q = _node_query(node)
    uuid = str(node.outbound.get("uuid") or "")
    encryption = q.get("encryption", "none") or "none"
    settings: dict[str, Any] = {"address": node.server, "port": node.port, "id": uuid, "encryption": encryption}
    flow = str(node.outbound.get("flow") or q.get("flow") or "")
    if flow: settings["flow"] = flow

    transport = str(node.extra.get("transport") or q.get("type") or q.get("network") or "raw").lower()
    method_map = {"tcp": "raw", "raw": "raw", "ws": "websocket", "websocket": "websocket", "grpc": "grpc",
                  "xhttp": "xhttp", "httpupgrade": "httpupgrade", "http-upgrade": "httpupgrade"}
    method = method_map.get(transport, transport if transport in {"raw","xhttp","grpc","websocket","httpupgrade","mkcp","hysteria"} else "raw")
    sec = str(node.extra.get("security") or q.get("security") or "none").lower()
    stream: dict[str, Any] = {"method": method, "security": sec}
    path = urllib.parse.unquote(q.get("path", ""))
    hosthdr = urllib.parse.unquote(q.get("host", ""))
    if method == "websocket":
        ws: dict[str, Any] = {}
        if path: ws["path"] = path
        if hosthdr: ws["host"] = hosthdr
        stream["wsSettings"] = ws
    elif method == "grpc":
        svc = urllib.parse.unquote(q.get("serviceName") or q.get("service_name") or q.get("service-name") or path or "")
        gs: dict[str, Any] = {}
        if svc: gs["serviceName"] = svc
        if q.get("authority"): gs["authority"] = urllib.parse.unquote(q["authority"])
        stream["grpcSettings"] = gs
    elif method == "xhttp":
        xs: dict[str, Any] = {}
        if path: xs["path"] = path
        if hosthdr: xs["host"] = hosthdr
        mode = q.get("mode", "")
        if mode: xs["mode"] = mode
        extra_raw = urllib.parse.unquote(q.get("extra", ""))
        if extra_raw:
            try:
                extra_obj = json.loads(extra_raw)
                if isinstance(extra_obj, dict): xs["extra"] = extra_obj
            except Exception:
                pass
        stream["xhttpSettings"] = xs
    elif method == "httpupgrade":
        hs: dict[str, Any] = {}
        if path: hs["path"] = path
        if hosthdr: hs["host"] = hosthdr
        stream["httpupgradeSettings"] = hs

    sni = urllib.parse.unquote(q.get("sni") or q.get("serverName") or q.get("servername") or "")
    fp = q.get("fp") or q.get("fingerprint") or q.get("client-fingerprint") or "chrome"
    insecure = _bool(q.get("allowInsecure") or q.get("insecure") or q.get("skip-cert-verify"))
    alpn = urllib.parse.unquote(q.get("alpn", ""))
    if sec == "tls":
        ts: dict[str, Any] = {"allowInsecure": insecure}
        if sni: ts["serverName"] = sni
        if fp: ts["fingerprint"] = fp
        if alpn: ts["alpn"] = _split_csv(alpn)
        stream["tlsSettings"] = ts
    elif sec == "reality":
        rs: dict[str, Any] = {"fingerprint": fp or "chrome"}
        if sni: rs["serverName"] = sni
        pub = q.get("pbk") or q.get("publicKey") or q.get("public_key") or ""
        if pub: rs["password"] = pub
        sid = q.get("sid") or q.get("shortId") or q.get("short_id") or ""
        if sid: rs["shortId"] = sid
        spx = urllib.parse.unquote(q.get("spx") or q.get("spiderX") or "")
        if spx: rs["spiderX"] = spx
        stream["realitySettings"] = rs
    return {"protocol": "vless", "tag": "proxy", "settings": settings, "streamSettings": stream}


def make_xray_test_config(node: Node, port: int, log_path: Path) -> dict[str, Any]:
    return {
        "log": {"loglevel": "warning", "error": str(log_path)},
        "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks", "settings": {"udp": True, "ip": "127.0.0.1"}, "tag": "test-in"}],
        "outbounds": [make_xray_vless_outbound(node), {"protocol": "freedom", "tag": "direct"}],
    }


def make_test_config(node: Node, port: int, log_path: Path) -> dict[str, Any]:
    out = copy.deepcopy(node.outbound); out["tag"] = "proxy"
    return {
        "log": {"level": "error", "timestamp": True, "output": str(log_path)},
        "inbounds": [{"type": "socks", "tag": "test-in", "listen": "127.0.0.1", "listen_port": port}],
        "outbounds": [out, {"type": "direct", "tag": "direct"}],
        "route": {
            "auto_detect_interface": True,
            "rules": [{"inbound": ["test-in"], "action": "route", "outbound": "proxy"}],
            "final": "direct",
        },
    }


def _wait_port(port: int, proc: subprocess.Popen[Any], timeout: float = 4.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None: return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15): return True
        except OSError:
            time.sleep(0.08)
    return False


def _recv_exact(s: socket.socket, n: int) -> bytes:
    b = bytearray()
    while len(b) < n:
        chunk = s.recv(n - len(b))
        if not chunk: raise OSError("socket closed")
        b.extend(chunk)
    return bytes(b)


def socks5_connect(proxy_port: int, host: str, port: int, timeout: float = 2.5) -> socket.socket:
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(b"\x05\x01\x00")
    if _recv_exact(s, 2) != b"\x05\x00": raise OSError("SOCKS auth")
    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 4: atyp, addr = 1, socket.inet_pton(socket.AF_INET, host)
        else: atyp, addr = 4, socket.inet_pton(socket.AF_INET6, host)
    except ValueError:
        enc = host.encode("idna"); atyp, addr = 3, bytes([len(enc)]) + enc
    s.sendall(b"\x05\x01\x00" + bytes([atyp]) + addr + struct.pack("!H", port))
    h = _recv_exact(s, 4)
    if h[1] != 0: raise OSError(f"SOCKS REP={h[1]}")
    if h[3] == 1: _recv_exact(s, 4)
    elif h[3] == 4: _recv_exact(s, 16)
    elif h[3] == 3: _recv_exact(s, _recv_exact(s, 1)[0])
    _recv_exact(s, 2)
    return s


def test_https(proxy_port: int, timeout: float = 3.0) -> tuple[bool, float | None]:
    start = time.perf_counter()
    s: socket.socket | None = None
    try:
        s = socks5_connect(proxy_port, "www.gstatic.com", 443, timeout)
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname="www.gstatic.com")
        ss.settimeout(timeout)
        ss.sendall(b"GET /generate_204 HTTP/1.1\r\nHost: www.gstatic.com\r\nConnection: close\r\n\r\n")
        data = ss.recv(256)
        ok = b"204" in data or b"200" in data
        ss.close()
        return ok, (time.perf_counter() - start) * 1000.0 if ok else None
    except Exception:
        try:
            if s: s.close()
        except Exception: pass
        return False, None


def _dns_query() -> bytes:
    tid = int(time.time() * 1000) & 0xFFFF
    hdr = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    qname = b"\x07example\x03com\x00"
    return hdr + qname + struct.pack("!HH", 1, 1)


def test_udp_via_socks(proxy_port: int, timeout: float = 2.8) -> bool:
    ctrl = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    ctrl.settimeout(timeout)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); udp.settimeout(timeout)
    try:
        ctrl.sendall(b"\x05\x01\x00")
        if _recv_exact(ctrl, 2) != b"\x05\x00": return False
        ctrl.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
        h = _recv_exact(ctrl, 4)
        if h[1] != 0: return False
        if h[3] == 1:
            bind = socket.inet_ntop(socket.AF_INET, _recv_exact(ctrl, 4))
        elif h[3] == 3:
            bind = _recv_exact(ctrl, _recv_exact(ctrl, 1)[0]).decode("ascii", "ignore")
        else:
            bind = "127.0.0.1"; _recv_exact(ctrl, 16)
        bport = struct.unpack("!H", _recv_exact(ctrl, 2))[0]
        if bind in {"0.0.0.0", "::", ""}: bind = "127.0.0.1"
        payload = _dns_query()
        pkt = b"\x00\x00\x00\x01" + socket.inet_aton("1.1.1.1") + struct.pack("!H", 53) + payload
        udp.sendto(pkt, (bind, bport))
        data, _ = udp.recvfrom(4096)
        if len(data) < 10 or data[0:2] != b"\x00\x00": return False
        atyp = data[3]; pos = 4
        if atyp == 1: pos += 4
        elif atyp == 4: pos += 16
        elif atyp == 3: pos += 1 + data[pos]
        pos += 2
        return len(data) > pos + 12
    except Exception:
        return False
    finally:
        try: udp.close()
        except Exception: pass
        try: ctrl.close()
        except Exception: pass


def _test_node_singbox(node: Node, singbox: Path, timeout: float = 3.0) -> Node:
    port = find_free_port()
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", node.name)[:40] or "node"
    cfg_path = RUNTIME_DIR / f"test_{threading.get_ident()}_{port}.json"
    log_path = RUNTIME_DIR / f"test_{safe}_{port}.log"
    cfg = make_test_config(node, port, log_path)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    node.tcp_total = len(GAME_TCP_ENDPOINTS)
    proc: subprocess.Popen[Any] | None = None
    try:
        chk = subprocess.run([str(singbox), "check", "-c", str(cfg_path)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=8)
        if chk.returncode != 0:
            node.valid = False; node.error = ((chk.stderr or chk.stdout or "config rejected").strip())[-800:]
            node.test_status = "Конфиг не поддержан"; return node
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0  # type: ignore[attr-defined]
        proc = subprocess.Popen([str(singbox), "run", "-c", str(cfg_path)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=flags)
        if not _wait_port(port, proc, 4.5):
            node.valid = False; node.error = "sing-box не запустил тестовый прокси"; node.test_status = "Не запустился"; return node
        ok, ms = test_https(port, timeout)
        node.https_ms = ms
        for host, p in GAME_TCP_ENDPOINTS:
            try:
                s = socks5_connect(port, host, p, timeout=timeout); s.close(); node.tcp_ok += 1
            except Exception:
                pass
        node.udp_ok = test_udp_via_socks(port, timeout=max(timeout, 2.8))
        # UDP is essential for this game; then reward real endpoint reachability and latency.
        score = 0.0
        if node.udp_ok: score += 700.0
        score += node.tcp_ok * 90.0
        if ok and ms is not None:
            # Реально различаем быстрые и медленные узлы: раньше всё >250 мс
            # получало одинаковый score, поэтому GUI мог выбрать заведомо более медленный сервер.
            score += 400.0 - min(ms, 1000.0) * 0.60
        else:
            score -= 250.0
        if not node.udp_ok: score -= 900.0
        node.score = score
        node.test_status = "OK" if node.udp_ok and ok and node.tcp_ok >= 2 else ("Без UDP" if not node.udp_ok else "Частично")
        return node
    except Exception as exc:
        node.valid = False; node.error = str(exc); node.test_status = "Ошибка"; return node
    finally:
        if proc and proc.poll() is None:
            try: proc.terminate(); proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
        try: cfg_path.unlink(missing_ok=True)
        except Exception: pass


def _test_node_xray(node: Node, xray: Path, timeout: float = 3.0) -> Node:
    port = find_free_port()
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", node.name)[:40] or "node"
    cfg_path = RUNTIME_DIR / f"xray_test_{threading.get_ident()}_{port}.json"
    log_path = RUNTIME_DIR / f"xray_test_{safe}_{port}.log"
    cfg = make_xray_test_config(node, port, log_path)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    node.tcp_total = len(GAME_TCP_ENDPOINTS); node.tcp_ok = 0; node.udp_ok = False; node.https_ms = None
    proc: subprocess.Popen[Any] | None = None
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0  # type: ignore[attr-defined]
        proc = subprocess.Popen([str(xray), "run", "-c", str(cfg_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        if not _wait_port(port, proc, 5.0):
            node.valid = False
            tail = ""
            try: tail = log_path.read_text(encoding="utf-8", errors="replace")[-1000:]
            except Exception: pass
            node.error = tail or "xray не запустил тестовый SOCKS"; node.test_status = "Xray не запустился"; return node
        ok, ms = test_https(port, timeout); node.https_ms = ms
        for host, p in GAME_TCP_ENDPOINTS:
            try:
                s = socks5_connect(port, host, p, timeout=timeout); s.close(); node.tcp_ok += 1
            except Exception: pass
        node.udp_ok = test_udp_via_socks(port, timeout=max(timeout, 2.8))
        score = (700.0 if node.udp_ok else -900.0) + node.tcp_ok * 90.0
        if ok and ms is not None:
            score += 400.0 - min(ms, 1000.0) * 0.60
        else:
            score -= 250.0
        node.score = score
        node.test_status = "OK (Xray)" if node.udp_ok and ok and node.tcp_ok >= 2 else ("Без UDP (Xray)" if not node.udp_ok else "Частично (Xray)")
        node.extra["engine"] = "xray"
        return node
    except Exception as exc:
        node.valid = False; node.error = str(exc); node.test_status = "Ошибка Xray"; return node
    finally:
        if proc and proc.poll() is None:
            try: proc.terminate(); proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
        try: cfg_path.unlink(missing_ok=True)
        except Exception: pass


def test_node(node: Node, singbox: Path, xray: Path | None = None, timeout: float = 3.0) -> Node:
    if node.protocol == "vless":
        if xray is None:
            node.valid = False; node.score = -5000.0; node.test_status = "Нужен Xray"
            node.error = "VLESS-транспорты этой версии тестируются через xray.exe, чтобы корректно поддержать XHTTP/gRPC/WS/REALITY."
            node.extra["engine"] = "xray"
            return node
        return _test_node_xray(node, xray, timeout)
    node.extra["engine"] = "sing-box"
    return _test_node_singbox(node, singbox, timeout)




def _download_any(urls: list[str], binary: bool = True, timeout: float = 25.0) -> tuple[bytes, str]:
    """Скачать первый доступный URL. GitHub RAW -> jsDelivr fallback."""
    last: Exception | None = None
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "ProstoKVNNetwork/0.20",
                    "Accept": "*/*",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if not data:
                raise RuntimeError("сервер вернул пустой файл")
            return data, url
        except Exception as exc:
            last = exc
    raise RuntimeError(f"не удалось скачать список: {last}")


def _normalize_domain_list(text: str) -> tuple[set[str], set[str], set[str], set[str]]:
    exact: set[str] = set()
    suffix: set[str] = set()
    regexes: set[str] = set()
    keywords: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!", "//")):
            continue
        low = line.lower()
        if low.startswith("domain:"):
            value = line[7:].strip().strip(".").lower()
            if value:
                suffix.add(value)
        elif low.startswith("full:"):
            value = line[5:].strip().strip(".").lower()
            if value:
                exact.add(value)
        elif low.startswith("regexp:"):
            value = line[7:].strip()
            if value:
                regexes.add(value)
        elif low.startswith("keyword:"):
            value = line[8:].strip()
            if value:
                keywords.add(value)
        else:
            # ITDog RAW — один домен на строку. Служебные/не-доменные строки пропускаем.
            value = line.split()[0].strip().strip(".").lower()
            if value and " " not in value and "/" not in value and ":" not in value:
                suffix.add(value)
    return exact, suffix, regexes, keywords


def _chunked(values: list[str], size: int = 6000) -> list[list[str]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def _build_domain_ruleset(texts: list[str], dest: Path) -> dict[str, int]:
    exact: set[str] = set()
    suffix: set[str] = set()
    regexes: set[str] = set()
    keywords: set[str] = set()
    for text in texts:
        e, s, r, k = _normalize_domain_list(text)
        exact.update(e); suffix.update(s); regexes.update(r); keywords.update(k)
    # Если домен уже есть как suffix, отдельный exact не нужен: в sing-box >=1.9
    # suffix без ведущей точки совпадает и с самим доменом, и с его поддоменами.
    exact.difference_update(suffix)
    rules: list[dict[str, Any]] = []
    for chunk in _chunked(sorted(suffix)):
        rules.append({"domain_suffix": chunk})
    for chunk in _chunked(sorted(exact)):
        rules.append({"domain": chunk})
    for chunk in _chunked(sorted(regexes), 1500):
        rules.append({"domain_regex": chunk})
    for chunk in _chunked(sorted(keywords), 1500):
        rules.append({"domain_keyword": chunk})
    payload = {"version": 3, "rules": rules}
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(dest)
    return {"suffix": len(suffix), "exact": len(exact), "regex": len(regexes), "keyword": len(keywords)}


def get_cached_ru_blocklists() -> list[Path]:
    # Порядок не принципиален: sing-box объединяет rule-set теги в одном route-правиле.
    paths = [BLOCKLIST_DIR / "ru_domains.json", BLOCKLIST_DIR / "service_domains.json"]
    paths += [BLOCKLIST_DIR / f"{name}.srs" for name in RUNETFREEDOM_IP_SOURCES]
    return [p for p in paths if p.is_file() and p.stat().st_size > 0]


def blocklists_age_seconds() -> float | None:
    try:
        data = json.loads(BLOCKLIST_META_PATH.read_text(encoding="utf-8"))
        ts = float(data.get("updated_at", 0))
        return max(0.0, time.time() - ts) if ts else None
    except Exception:
        return None


def update_ru_blocklists(log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Обновить доменные и IP-списки РФ. При частичном сбое оставляет старый кэш."""
    def emit(msg: str) -> None:
        if log:
            try: log(msg)
            except Exception: pass

    texts: list[str] = []
    used_sources: list[str] = []
    domain_errors: list[str] = []
    for label, urls in (("ITDog Russia inside", ITDOG_DOMAIN_URLS), ("RunetFreedom ru-blocked", RUNETFREEDOM_DOMAIN_URLS)):
        try:
            data, used = _download_any(urls, binary=False)
            text = data.decode("utf-8", errors="replace")
            texts.append(text); used_sources.append(used)
            emit(f"Список {label}: загружен ({len(text.splitlines())} строк)")
        except Exception as exc:
            domain_errors.append(f"{label}: {exc}")
            emit(f"Список {label}: ошибка загрузки ({exc})")

    domain_path = BLOCKLIST_DIR / "ru_domains.json"
    counts: dict[str, int] = {"suffix": 0, "exact": 0, "regex": 0, "keyword": 0}
    if texts:
        counts = _build_domain_ruleset(texts, domain_path)
    elif not domain_path.exists():
        raise RuntimeError("Не удалось получить доменные списки РФ и локального кэша ещё нет. " + "; ".join(domain_errors))
    else:
        emit("Доменные списки: используется предыдущий локальный кэш")

    # Отдельно собираем известные сервисы. Это закрывает YouTube CDN/API, Discord,
    # Meta/Instagram, X/Twitter и TikTok, даже если общий список отстаёт.
    service_texts: list[str] = [YOUTUBE_FALLBACK]
    service_errors: list[str] = []
    service_loaded: list[str] = []
    for service, urls in ITDOG_SERVICE_SOURCES.items():
        try:
            data, used = _download_any(urls, binary=False)
            text = data.decode("utf-8", errors="replace")
            service_texts.append(text)
            service_loaded.append(service)
            used_sources.append(used)
            emit(f"Сервис {service}: загружен ({len(text.splitlines())} доменов)")
        except Exception as exc:
            service_errors.append(f"{service}: {exc}")
            emit(f"Сервис {service}: ошибка загрузки ({exc})")

    service_path = BLOCKLIST_DIR / "service_domains.json"
    service_counts: dict[str, int] = {"suffix": 0, "exact": 0, "regex": 0, "keyword": 0}
    try:
        service_counts = _build_domain_ruleset(service_texts, service_path)
    except Exception as exc:
        service_errors.append(f"service ruleset: {exc}")
        if service_path.exists() and service_path.stat().st_size > 0:
            emit("Сервисные домены: используется предыдущий локальный кэш")
        else:
            raise

    ip_paths: list[Path] = []
    ip_errors: list[str] = []
    for name, urls in RUNETFREEDOM_IP_SOURCES.items():
        dest = BLOCKLIST_DIR / f"{name}.srs"
        try:
            data, used = _download_any(urls, binary=True)
            tmp = dest.with_suffix(".srs.tmp")
            tmp.write_bytes(data); tmp.replace(dest)
            used_sources.append(used); ip_paths.append(dest)
            emit(f"IP rule-set {name}: обновлён ({len(data) // 1024} КБ)")
        except Exception as exc:
            ip_errors.append(f"{name}: {exc}")
            if dest.exists() and dest.stat().st_size > 0:
                ip_paths.append(dest); emit(f"IP rule-set {name}: используется кэш")
            else:
                emit(f"IP rule-set {name}: недоступен ({exc})")

    paths = ([domain_path] if domain_path.exists() else []) + ([service_path] if service_path.exists() else []) + ip_paths
    meta = {
        "updated_at": time.time(),
        "updated_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "counts": counts,
        "service_counts": service_counts,
        "services": service_loaded,
        "paths": [str(x) for x in paths],
        "sources": used_sources,
        "errors": domain_errors + service_errors + ip_errors,
    }
    try:
        BLOCKLIST_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return meta


def _rule_sets_for_paths(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    defs: list[dict[str, Any]] = []
    tags: list[str] = []
    for i, path in enumerate(paths):
        if not path.exists():
            continue
        tag = f"ru_block_{i}"
        fmt = "binary" if path.suffix.lower() == ".srs" else "source"
        defs.append({"type": "local", "tag": tag, "format": fmt, "path": str(path)})
        tags.append(tag)
    return defs, tags

def make_tun_config(
    node: Node,
    log_path: Path,
    force_game_vpn: bool = True,
    discord_vpn: bool = False,
    steam_webhelper_vpn: bool = False,
    blocked_ru_vpn: bool = True,
    blocklist_paths: list[Path] | None = None,
    proxy_override: dict[str, Any] | None = None,
    route_mode: str = "smart_ru",
    discord_mode: str = "direct",
) -> dict[str, Any]:
    # Для VLESS Xray поднимается локальным SOCKS-мостом. В старой v3 proxy_override
    # вычислялся, но по ошибке не использовался — здесь это исправлено.
    out = copy.deepcopy(proxy_override if proxy_override is not None else node.outbound)
    out["tag"] = "proxy"
    rules: list[dict[str, Any]] = [
        # DNS перехватывается до sniff. reverse_mapping ниже сохраняет домен для
        # последующего соединения — сервисные списки стабильнее работают в браузерах.
        {"network": ["tcp", "udp"], "port": [53], "action": "hijack-dns"},
        {"action": "sniff"},
        {"process_name": PROTECTED_DIRECT, "action": "route", "outbound": "direct"},
        {"process_name": ["steam.exe", "GameOverlayUI.exe"], "action": "route", "outbound": "direct"},
    ]
    if force_game_vpn:
        rules.append({"process_name": TARGET_PROCESSES, "action": "route", "outbound": "proxy"})

    # Discord Voice использует отдельный UDP канал с портом, который сообщает
    # конкретный voice server. Поэтому не ограничиваем UDP выдуманным диапазоном:
    # весь Discord идёт одним маршрутом через VPN — и gateway, и voice UDP.
    if route_mode in {"smart_ru", "game_only"} or discord_mode == "all_vpn" or discord_vpn:
        rules.append({"process_name": DISCORD_PROCESSES, "action": "route", "outbound": "proxy"})

    # Telegram Desktop часто подключается непосредственно к IP, где доменный
    # rule-set уже не помогает. В умной стратегии процесс пускаем через VPN.
    if route_mode == "smart_ru":
        rules.append({"process_name": TELEGRAM_PROCESSES, "action": "route", "outbound": "proxy"})

    if steam_webhelper_vpn:
        rules.append({"process_name": ["steamwebhelper.exe"], "action": "route", "outbound": "proxy"})

    # Обычные российские сайты не должны тратить VPN-трафик и получать лишний пинг.
    # Правило стоит выше ru-blocked/service rule-set, поэтому .ru/.su/.рф в браузере
    # всегда идут DIRECT. Процессные правила игр/Discord/Telegram выше и
    # сохраняют свой VPN-маршрут независимо от доменной зоны.
    rules.append({
        "domain_suffix": RU_DIRECT_DOMAIN_SUFFIXES,
        "action": "route",
        "outbound": "direct",
    })

    rule_defs: list[dict[str, Any]] = []
    if route_mode == "smart_ru" and blocked_ru_vpn and blocklist_paths:
        rule_defs, tags = _rule_sets_for_paths(blocklist_paths)
        if tags:
            rules.append({"rule_set": tags, "action": "route", "outbound": "proxy"})

    final_outbound = "proxy" if route_mode == "global" else "direct"
    route: dict[str, Any] = {"auto_detect_interface": True, "rules": rules, "final": final_outbound}
    if rule_defs:
        route["rule_set"] = rule_defs

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
            "type": "tun", "tag": "prostokvn-tun", "interface_name": "prostokvn_network_tun",
            "address": ["172.29.77.1/30"], "mtu": 1400, "auto_route": True,
            "strict_route": False, "stack": "system",
        }],
        "outbounds": [out, {"type": "direct", "tag": "direct"}],
        "route": route,
        "experimental": {"clash_api": {"external_controller": "127.0.0.1:19181", "secret": ""}},
    }


def is_admin() -> bool:
    if os.name != "nt": return True
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False


class TunRunner:
    def __init__(
        self, singbox: Path, node: Node,
        discord_vpn: bool = False, steam_webhelper_vpn: bool = False, xray: Path | None = None,
        force_game_vpn: bool = True, blocked_ru_vpn: bool = True, blocklist_paths: list[Path] | None = None,
        route_mode: str = "smart_ru", discord_mode: str = "direct",
    ):
        self.singbox = singbox; self.xray = xray; self.node = node
        self.discord_vpn = discord_vpn; self.steam_webhelper_vpn = steam_webhelper_vpn
        self.force_game_vpn = force_game_vpn; self.blocked_ru_vpn = blocked_ru_vpn
        self.route_mode = route_mode; self.discord_mode = discord_mode
        self.blocklist_paths = list(blocklist_paths or [])
        self.proc: subprocess.Popen[Any] | None = None
        self.xray_proc: subprocess.Popen[Any] | None = None
        self.cfg_path = RUNTIME_DIR / "active_tun.json"
        self.log_path = RUNTIME_DIR / "active_tun.log"
        self.xray_cfg_path = RUNTIME_DIR / "active_xray.json"
        self.xray_log_path = RUNTIME_DIR / "active_xray.log"

    def _start_xray_bridge(self) -> dict[str, Any]:
        if not self.xray: raise RuntimeError("Для выбранного VLESS-узла нужен xray.exe")
        port = find_free_port()
        cfg = make_xray_test_config(self.node, port, self.xray_log_path)
        self.xray_cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0  # type: ignore[attr-defined]
        self.xray_proc = subprocess.Popen([str(self.xray), "run", "-c", str(self.xray_cfg_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        if not _wait_port(port, self.xray_proc, 6.0):
            tail = ""
            try: tail = self.xray_log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            except Exception: pass
            raise RuntimeError("Xray не смог поднять выбранный VLESS-узел:\n" + (tail or "нет подробностей"))
        return {"type": "socks", "tag": "proxy", "server": "127.0.0.1", "server_port": port, "version": "5"}

    def start(self) -> None:
        if self.proc and self.proc.poll() is None: return
        proxy_override = None
        if self.node.protocol == "vless":
            proxy_override = self._start_xray_bridge()
        cfg = make_tun_config(
            self.node, self.log_path,
            force_game_vpn=self.force_game_vpn,
            discord_vpn=self.discord_vpn,
            steam_webhelper_vpn=self.steam_webhelper_vpn,
            blocked_ru_vpn=self.blocked_ru_vpn,
            blocklist_paths=self.blocklist_paths,
            proxy_override=proxy_override,
            route_mode=self.route_mode,
            discord_mode=self.discord_mode,
        )
        self.cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        chk = subprocess.run([str(self.singbox), "check", "-c", str(self.cfg_path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        if chk.returncode != 0:
            self.stop()
            raise RuntimeError("sing-box отклонил рабочий конфиг:\n" + ((chk.stderr or chk.stdout or "").strip())[-1600:])
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0  # type: ignore[attr-defined]
        self.proc = subprocess.Popen([str(self.singbox), "run", "-c", str(self.cfg_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        end = time.time() + 8
        while time.time() < end:
            if self.proc.poll() is not None:
                tail = ""
                try: tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                except Exception: pass
                self.stop(); raise RuntimeError("TUN завершился при запуске:\n" + tail)
            if _interface_probably_exists("prostokvn_network_tun"): return
            time.sleep(0.25)
        if self.proc.poll() is not None:
            self.stop(); raise RuntimeError("TUN не запустился")

    def stop(self) -> None:
        for proc in (self.proc, self.xray_proc):
            if proc and proc.poll() is None:
                try: proc.terminate(); proc.wait(timeout=4)
                except Exception:
                    try: proc.kill()
                    except Exception: pass
        self.proc = None; self.xray_proc = None
        for p in (self.cfg_path, self.xray_cfg_path):
            try: p.unlink(missing_ok=True)
            except Exception: pass

    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)


def _interface_probably_exists(name: str) -> bool:
    if os.name != "nt": return True
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-NetAdapter -Name '{name}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"],
                           capture_output=True, text=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)  # type: ignore[attr-defined]
        return name.lower() in (r.stdout or "").lower()
    except Exception:
        return False


def protocol_summary(nodes: list[Node]) -> dict[str, int]:
    d: dict[str, int] = {}
    for n in nodes:
        key = n.stack_label()
        d[key] = d.get(key, 0) + 1
    return d
