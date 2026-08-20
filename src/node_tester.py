# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Проверка узлов без утечек дочерних процессов.

Каждый тестовый xray/sing-box запускается через PROCESS_MANAGER, получает
уникальный runtime-конфиг и всегда завершается в finally. Формирование VLESS
вынесено в protocol_engine и больше не зависит от monkey-patch.
"""

import copy
import json
from pathlib import Path
import re
import socket
import ssl
import statistics
import struct
import subprocess
import threading
import time
from typing import Any

from nodes import Node
from paths import RUNTIME_DIR
from process_manager import PROCESS_MANAGER, process_alive
from protocol_engine import (
    choose_engine,
    fatal_issues,
    make_xray_test_config,
    make_xray_vless_outbound,
    singbox_outbound,
    validate_node,
)

HTTPS_HOST = "www.gstatic.com"
HTTPS_PATH = "/generate_204"
TCP_CHECKS = [
    ("www.gstatic.com", 443),
    ("www.cloudflare.com", 443),
]
HTTPS_ATTEMPTS = 3


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_test_config(node: Node, port: int, log_path: Path) -> dict[str, Any]:
    outbound = singbox_outbound(node)
    return {
        "log": {"level": "error", "timestamp": True, "output": str(log_path)},
        "inbounds": [{
            "type": "socks",
            "tag": "test-in",
            "listen": "127.0.0.1",
            "listen_port": port,
        }],
        "outbounds": [outbound, {"type": "direct", "tag": "direct"}],
        "route": {
            "auto_detect_interface": True,
            "rules": [{"inbound": ["test-in"], "action": "route", "outbound": "proxy"}],
            "final": "direct",
        },
    }


def _wait_port(port: int, proc: subprocess.Popen[Any], timeout: float = 4.0) -> bool:
    end = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < end:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                return True
        except OSError:
            time.sleep(0.08)
    return False


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("SOCKS соединение закрыто")
        data.extend(chunk)
    return bytes(data)


def socks5_connect(proxy_port: int, host: str, port: int, timeout: float = 3.0) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    sock.settimeout(timeout)
    sock.sendall(b"\x05\x01\x00")
    if _recv_exact(sock, 2) != b"\x05\x00":
        sock.close()
        raise OSError("SOCKS5 authentication rejected")

    try:
        packed = socket.inet_pton(socket.AF_INET, host)
        request = b"\x05\x01\x00\x01" + packed + struct.pack("!H", port)
    except OSError:
        try:
            packed6 = socket.inet_pton(socket.AF_INET6, host)
            request = b"\x05\x01\x00\x04" + packed6 + struct.pack("!H", port)
        except OSError:
            encoded = host.encode("idna")
            if len(encoded) > 255:
                sock.close()
                raise OSError("Слишком длинное имя хоста")
            request = b"\x05\x01\x00\x03" + bytes([len(encoded)]) + encoded + struct.pack("!H", port)

    sock.sendall(request)
    header = _recv_exact(sock, 4)
    if header[1] != 0:
        sock.close()
        raise OSError(f"SOCKS5 connect failed: {header[1]}")
    if header[3] == 1:
        _recv_exact(sock, 4)
    elif header[3] == 4:
        _recv_exact(sock, 16)
    elif header[3] == 3:
        _recv_exact(sock, _recv_exact(sock, 1)[0])
    _recv_exact(sock, 2)
    return sock


def _https_once(proxy_port: int, timeout: float) -> float | None:
    started = time.perf_counter()
    raw_socket: socket.socket | None = None
    secure_socket: ssl.SSLSocket | None = None
    try:
        raw_socket = socks5_connect(proxy_port, HTTPS_HOST, 443, timeout)
        context = ssl.create_default_context()
        secure_socket = context.wrap_socket(raw_socket, server_hostname=HTTPS_HOST)
        secure_socket.settimeout(timeout)
        request = (
            f"GET {HTTPS_PATH} HTTP/1.1\r\n"
            f"Host: {HTTPS_HOST}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        secure_socket.sendall(request)
        data = secure_socket.recv(256)
        if b"204" not in data and b"200" not in data:
            return None
        return (time.perf_counter() - started) * 1000.0
    except Exception:
        return None
    finally:
        try:
            if secure_socket is not None:
                secure_socket.close()
            elif raw_socket is not None:
                raw_socket.close()
        except Exception:
            pass


def measure_https(proxy_port: int, timeout: float = 3.0, attempts: int = HTTPS_ATTEMPTS) -> tuple[int, float | None]:
    values: list[float] = []
    for _ in range(max(1, attempts)):
        latency = _https_once(proxy_port, timeout)
        if latency is not None:
            values.append(latency)
    return len(values), statistics.median(values) if values else None


def _dns_query() -> bytes:
    transaction_id = int(time.time() * 1000) & 0xFFFF
    header = struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
    qname = b"\x07example\x03com\x00"
    return header + qname + struct.pack("!HH", 1, 1)


def test_udp_via_socks(proxy_port: int, timeout: float = 2.8) -> bool:
    control: socket.socket | None = None
    udp: socket.socket | None = None
    try:
        control = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
        control.settimeout(timeout)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.settimeout(timeout)

        control.sendall(b"\x05\x01\x00")
        if _recv_exact(control, 2) != b"\x05\x00":
            return False
        control.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
        header = _recv_exact(control, 4)
        if header[1] != 0:
            return False

        if header[3] == 1:
            bind = socket.inet_ntop(socket.AF_INET, _recv_exact(control, 4))
        elif header[3] == 3:
            bind = _recv_exact(control, _recv_exact(control, 1)[0]).decode("ascii", "ignore")
        else:
            bind = "127.0.0.1"
            _recv_exact(control, 16)
        bind_port = struct.unpack("!H", _recv_exact(control, 2))[0]
        if bind in {"0.0.0.0", "::", ""}:
            bind = "127.0.0.1"

        payload = _dns_query()
        packet = b"\x00\x00\x00\x01" + socket.inet_aton("1.1.1.1") + struct.pack("!H", 53) + payload
        udp.sendto(packet, (bind, bind_port))
        data, _ = udp.recvfrom(4096)
        if len(data) < 10 or data[:2] != b"\x00\x00":
            return False
        address_type = data[3]
        position = 4
        if address_type == 1:
            position += 4
        elif address_type == 4:
            position += 16
        elif address_type == 3:
            position += 1 + data[position]
        position += 2
        return len(data) > position + 12
    except Exception:
        return False
    finally:
        for sock in (udp, control):
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass


def _test_tcp_targets(proxy_port: int, timeout: float) -> tuple[int, int]:
    success = 0
    for host, port in TCP_CHECKS:
        sock: socket.socket | None = None
        try:
            sock = socks5_connect(proxy_port, host, port, timeout=timeout)
            success += 1
        except Exception:
            pass
        finally:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
    return success, len(TCP_CHECKS)


def _apply_health_score(node: Node, https_success: int, https_ms: float | None) -> None:
    attempts = HTTPS_ATTEMPTS
    stability = https_success / attempts
    tcp_ratio = node.tcp_ok / node.tcp_total if node.tcp_total else 0.0
    score = stability * 600.0 + tcp_ratio * 200.0
    if node.udp_ok:
        score += 180.0
    if https_ms is not None:
        score += max(0.0, 320.0 - min(https_ms, 1600.0) * 0.20)
    else:
        score -= 600.0

    node.https_ms = https_ms
    node.score = score
    node.extra["stability"] = round(stability, 3)
    node.extra["https_success"] = https_success
    node.extra["https_attempts"] = attempts

    if https_success == attempts and node.udp_ok:
        node.test_status = f"OK {https_success}/{attempts}"
    elif https_success >= 2:
        node.test_status = f"Стабильно {https_success}/{attempts}" + ("" if node.udp_ok else " · без UDP")
    elif https_success == 1:
        node.test_status = "Нестабильно 1/3"
    else:
        node.test_status = "HTTPS недоступен"


def _cleanup_test_logs(keep: int = 8) -> None:
    files = list(RUNTIME_DIR.glob("test_*.log")) + list(RUNTIME_DIR.glob("xray_test_*.log"))
    files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    for path in files[keep:]:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _mark_validation_failure(node: Node) -> Node:
    errors = fatal_issues(node)
    if not errors:
        return node
    node.valid = False
    node.score = -5000.0
    node.error = "\n".join(issue.message for issue in errors)
    node.test_status = "Некорректный профиль"
    return node


def _test_node_singbox(node: Node, singbox: Path, timeout: float = 3.0) -> Node:
    if fatal_issues(node):
        return _mark_validation_failure(node)

    port = find_free_port()
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", node.name)[:40] or "node"
    config_path = RUNTIME_DIR / f"test_{threading.get_ident()}_{port}.json"
    log_path = RUNTIME_DIR / f"test_{safe_name}_{port}.log"
    config_path.write_text(json.dumps(make_test_config(node, port, log_path), ensure_ascii=False, indent=2), encoding="utf-8")
    process: subprocess.Popen[Any] | None = None

    try:
        check = subprocess.run(
            [str(singbox), "check", "-c", str(config_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if check.returncode != 0:
            node.valid = False
            node.error = ((check.stderr or check.stdout or "config rejected").strip())[-1200:]
            node.test_status = "Конфиг не поддержан"
            return node

        process = PROCESS_MANAGER.spawn(
            [str(singbox), "run", "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_port(port, process, 4.5):
            node.valid = False
            node.error = _read_log_tail(log_path) or "sing-box не запустил тестовый прокси"
            node.test_status = "Не запустился"
            return node

        https_success, latency = measure_https(port, timeout)
        node.tcp_ok, node.tcp_total = _test_tcp_targets(port, timeout)
        node.udp_ok = test_udp_via_socks(port, timeout=max(timeout, 2.8))
        _apply_health_score(node, https_success, latency)
        node.extra["engine"] = "sing-box"
        return node
    except Exception as exc:
        node.valid = False
        node.error = str(exc)
        node.test_status = "Ошибка"
        return node
    finally:
        PROCESS_MANAGER.stop(process)
        try:
            config_path.unlink(missing_ok=True)
        except Exception:
            pass
        if node.valid and node.https_ms is not None:
            try:
                log_path.unlink(missing_ok=True)
            except Exception:
                pass
        _cleanup_test_logs()


def _test_node_xray(node: Node, xray: Path, timeout: float = 3.0) -> Node:
    if fatal_issues(node):
        return _mark_validation_failure(node)

    port = find_free_port()
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", node.name)[:40] or "node"
    config_path = RUNTIME_DIR / f"xray_test_{threading.get_ident()}_{port}.json"
    log_path = RUNTIME_DIR / f"xray_test_{safe_name}_{port}.log"
    config_path.write_text(json.dumps(make_xray_test_config(node, port, log_path), ensure_ascii=False, indent=2), encoding="utf-8")
    process: subprocess.Popen[Any] | None = None

    try:
        process = PROCESS_MANAGER.spawn(
            [str(xray), "run", "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_port(port, process, 5.5):
            node.valid = False
            node.error = _read_log_tail(log_path) or "Xray не запустил тестовый SOCKS"
            node.test_status = "Xray не запустился"
            return node

        https_success, latency = measure_https(port, timeout)
        node.tcp_ok, node.tcp_total = _test_tcp_targets(port, timeout)
        node.udp_ok = test_udp_via_socks(port, timeout=max(timeout, 2.8))
        _apply_health_score(node, https_success, latency)
        node.extra["engine"] = "xray"
        return node
    except Exception as exc:
        node.valid = False
        node.error = str(exc)
        node.test_status = "Ошибка Xray"
        return node
    finally:
        PROCESS_MANAGER.stop(process)
        try:
            config_path.unlink(missing_ok=True)
        except Exception:
            pass
        if node.valid and node.https_ms is not None:
            try:
                log_path.unlink(missing_ok=True)
            except Exception:
                pass
        _cleanup_test_logs()


def _read_log_tail(path: Path, limit: int = 1600) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:].strip()
    except Exception:
        return ""


def test_node(node: Node, singbox: Path, xray: Path | None = None, timeout: float = 3.0) -> Node:
    node.tcp_ok = 0
    node.tcp_total = 0
    node.udp_ok = False
    node.https_ms = None
    node.score = -999999.0

    if not node.valid:
        return node
    if fatal_issues(node):
        return _mark_validation_failure(node)

    plan = choose_engine(node, xray_available=xray is not None)
    node.extra["engine_plan"] = plan.engine
    warnings = [issue.message for issue in validate_node(node) if issue.level == "warning"]
    if warnings:
        node.extra["protocol_warnings"] = warnings

    if plan.engine == "xray":
        if xray is None:
            node.valid = False
            node.score = -5000.0
            node.test_status = "Нужен Xray"
            node.error = plan.reason
            node.extra["engine"] = "xray"
            return node
        return _test_node_xray(node, xray, timeout)
    return _test_node_singbox(node, singbox, timeout)


def protocol_summary(nodes: list[Node]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for node in nodes:
        key = node.stack_label()
        summary[key] = summary.get(key, 0) + 1
    return summary
