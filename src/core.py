# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
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

from paths import (
    APP_DIR, RUNTIME_DIR, USER_DATA_DIR, BLOCKLIST_DIR, SETTINGS_PATH,
    MANAGED_CORE_DIR, BLOCKLIST_META_PATH,
)

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


from nodes import Node, download_subscription, _bool, _split_csv

def find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0)); port = int(s.getsockname()[1]); s.close(); return port



from cores import install_official_cores, find_singbox_binary, find_xray_binary

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
