# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import copy
import ipaddress
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
import urllib.parse
from typing import Any

from nodes import Node, _bool, _split_csv
from paths import RUNTIME_DIR

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


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value if str(item))
    return str(value or "")


def _header_value(headers: Any, name: str) -> str:
    if not isinstance(headers, dict):
        return ""
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value or "")
    return ""


def _node_query(node: Node) -> dict[str, str]:
    """Возвращает Xray-параметры VLESS независимо от формата подписки."""
    query = node.extra.get("query")
    if isinstance(query, dict) and query:
        return {str(key): str(value) for key, value in query.items()}

    if node.source.lower().startswith("vless://"):
        parsed = urllib.parse.urlsplit(node.source)
        values = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        return {key: (items[0] if items else "") for key, items in values.items()}

    result: dict[str, str] = {}

    # VLESS из sing-box JSON и нормализованный Clash outbound уже содержит
    # transport/tls в структурированном виде. Переводим их обратно в поля,
    # которые использует Xray builder.
    outbound = node.outbound if isinstance(node.outbound, dict) else {}
    if outbound.get("flow"):
        result["flow"] = str(outbound.get("flow") or "")

    transport = outbound.get("transport")
    if isinstance(transport, dict):
        transport_type = str(transport.get("type") or "raw").lower()
        result["type"] = transport_type
        if transport.get("path"):
            result["path"] = str(transport.get("path") or "")
        host = transport.get("host")
        if isinstance(host, list):
            host = host[0] if host else ""
        if host:
            result["host"] = str(host)
        headers = transport.get("headers")
        header_host = _header_value(headers, "host")
        if header_host and not result.get("host"):
            result["host"] = header_host
        if isinstance(headers, dict) and headers:
            result["_headers"] = json.dumps(headers, ensure_ascii=False)
        service = transport.get("service_name") or transport.get("serviceName")
        if service:
            result["serviceName"] = str(service)
        if transport.get("authority"):
            result["authority"] = str(transport.get("authority") or "")
        if transport.get("mode"):
            result["mode"] = str(transport.get("mode") or "")
        if isinstance(transport.get("extra"), dict):
            result["extra"] = json.dumps(transport["extra"], ensure_ascii=False)

    tls = outbound.get("tls")
    if isinstance(tls, dict) and _bool(tls.get("enabled", True)):
        reality = tls.get("reality") if isinstance(tls.get("reality"), dict) else None
        result["security"] = "reality" if reality else "tls"
        if tls.get("server_name"):
            result["sni"] = str(tls.get("server_name") or "")
        if tls.get("insecure") is not None:
            result["allowInsecure"] = "true" if _bool(tls.get("insecure")) else "false"
        if tls.get("alpn"):
            result["alpn"] = _csv_value(tls.get("alpn"))
        utls = tls.get("utls") if isinstance(tls.get("utls"), dict) else None
        if utls and utls.get("fingerprint"):
            result["fp"] = str(utls.get("fingerprint") or "")
        if reality:
            public_key = reality.get("public_key") or reality.get("publicKey")
            short_id = reality.get("short_id") or reality.get("shortId")
            if public_key:
                result["pbk"] = str(public_key)
            if short_id:
                result["sid"] = str(short_id)

    # Clash хранит часть критичных параметров во вложенных *-opts. Они не
    # попадали в старый scalar-only flatten и из-за этого WS/gRPC/REALITY
    # ломались именно для YAML-подписок.
    clash = node.extra.get("clash")
    if isinstance(clash, dict):
        network = str(clash.get("network") or result.get("type") or "raw").lower()
        result["type"] = network

        reality_opts = clash.get("reality-opts")
        if not isinstance(reality_opts, dict):
            reality_opts = clash.get("reality_opts")
        if isinstance(reality_opts, dict):
            result["security"] = "reality"
            public_key = reality_opts.get("public-key") or reality_opts.get("public_key")
            short_id = reality_opts.get("short-id") or reality_opts.get("short_id")
            if public_key:
                result["pbk"] = str(public_key)
            if short_id:
                result["sid"] = str(short_id)
        elif _bool(clash.get("tls")):
            result["security"] = "tls"

        sni = clash.get("servername") or clash.get("sni")
        if sni:
            result["sni"] = str(sni)
        fingerprint = clash.get("client-fingerprint") or clash.get("fingerprint")
        if fingerprint:
            result["fp"] = str(fingerprint)
        if clash.get("skip-cert-verify") is not None:
            result["allowInsecure"] = "true" if _bool(clash.get("skip-cert-verify")) else "false"
        if clash.get("alpn"):
            result["alpn"] = _csv_value(clash.get("alpn"))
        if clash.get("flow"):
            result["flow"] = str(clash.get("flow") or "")

        if network in {"ws", "websocket"}:
            opts = clash.get("ws-opts") or clash.get("ws_opts") or {}
            if isinstance(opts, dict):
                if opts.get("path"):
                    result["path"] = str(opts.get("path") or "")
                headers = opts.get("headers")
                host = _header_value(headers, "host")
                if host:
                    result["host"] = host
                if isinstance(headers, dict) and headers:
                    result["_headers"] = json.dumps(headers, ensure_ascii=False)
        elif network == "grpc":
            opts = clash.get("grpc-opts") or clash.get("grpc_opts") or {}
            if isinstance(opts, dict):
                service = opts.get("grpc-service-name") or opts.get("service-name") or opts.get("service_name")
                if service:
                    result["serviceName"] = str(service)
                if opts.get("authority"):
                    result["authority"] = str(opts.get("authority") or "")
        elif network == "xhttp":
            opts = clash.get("xhttp-opts") or clash.get("xhttp_opts") or {}
            if isinstance(opts, dict):
                if opts.get("path"):
                    result["path"] = str(opts.get("path") or "")
                if opts.get("host"):
                    result["host"] = str(opts.get("host") or "")
                if opts.get("mode"):
                    result["mode"] = str(opts.get("mode") or "")
                if isinstance(opts.get("extra"), dict):
                    result["extra"] = json.dumps(opts["extra"], ensure_ascii=False)
        elif network in {"httpupgrade", "http-upgrade"}:
            opts = clash.get("http-upgrade-opts") or clash.get("httpupgrade-opts") or {}
            if isinstance(opts, dict):
                if opts.get("path"):
                    result["path"] = str(opts.get("path") or "")
                if opts.get("host"):
                    result["host"] = str(opts.get("host") or "")

    return result


def make_xray_vless_outbound(node: Node) -> dict[str, Any]:
    if node.protocol != "vless":
        raise ValueError("Xray builder используется только для VLESS")

    query = _node_query(node)
    uuid = str(node.outbound.get("uuid") or "")
    encryption = query.get("encryption", "none") or "none"
    settings: dict[str, Any] = {
        "address": node.server,
        "port": node.port,
        "id": uuid,
        "encryption": encryption,
    }

    flow = str(node.outbound.get("flow") or query.get("flow") or "")
    if flow:
        settings["flow"] = flow

    transport = str(
        node.extra.get("transport")
        or query.get("type")
        or query.get("network")
        or "raw"
    ).lower()
    method_map = {
        "tcp": "raw",
        "raw": "raw",
        "ws": "websocket",
        "websocket": "websocket",
        "grpc": "grpc",
        "xhttp": "xhttp",
        "httpupgrade": "httpupgrade",
        "http-upgrade": "httpupgrade",
    }
    supported = {"raw", "xhttp", "grpc", "websocket", "httpupgrade", "mkcp", "hysteria"}
    method = method_map.get(transport, transport if transport in supported else "raw")
    security = str(node.extra.get("security") or query.get("security") or "none").lower()
    stream: dict[str, Any] = {"method": method, "security": security}

    path = urllib.parse.unquote(query.get("path", ""))
    host = urllib.parse.unquote(query.get("host", ""))
    if method == "websocket":
        ws: dict[str, Any] = {}
        if path:
            ws["path"] = path
        if host:
            ws["host"] = host
        headers_raw = query.get("_headers", "")
        if headers_raw:
            try:
                headers = json.loads(headers_raw)
                if isinstance(headers, dict):
                    ws["headers"] = {str(k): str(v) for k, v in headers.items()}
            except Exception:
                pass
        stream["wsSettings"] = ws
    elif method == "grpc":
        service = urllib.parse.unquote(
            query.get("serviceName")
            or query.get("service_name")
            or query.get("service-name")
            or path
            or ""
        )
        grpc: dict[str, Any] = {}
        if service:
            grpc["serviceName"] = service
        if query.get("authority"):
            grpc["authority"] = urllib.parse.unquote(query["authority"])
        stream["grpcSettings"] = grpc
    elif method == "xhttp":
        xhttp: dict[str, Any] = {}
        if path:
            xhttp["path"] = path
        if host:
            xhttp["host"] = host
        mode = query.get("mode", "")
        if mode:
            xhttp["mode"] = mode
        extra_raw = urllib.parse.unquote(query.get("extra", ""))
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
                if isinstance(extra, dict):
                    xhttp["extra"] = extra
            except Exception:
                pass
        stream["xhttpSettings"] = xhttp
    elif method == "httpupgrade":
        upgrade: dict[str, Any] = {}
        if path:
            upgrade["path"] = path
        if host:
            upgrade["host"] = host
        stream["httpupgradeSettings"] = upgrade

    sni = urllib.parse.unquote(
        query.get("sni") or query.get("serverName") or query.get("servername") or ""
    )
    fingerprint = query.get("fp") or query.get("fingerprint") or query.get("client-fingerprint") or "chrome"
    insecure = _bool(query.get("allowInsecure") or query.get("insecure") or query.get("skip-cert-verify"))
    alpn = urllib.parse.unquote(query.get("alpn", ""))

    if security == "tls":
        tls: dict[str, Any] = {"allowInsecure": insecure}
        if sni:
            tls["serverName"] = sni
        if fingerprint:
            tls["fingerprint"] = fingerprint
        if alpn:
            tls["alpn"] = _split_csv(alpn)
        stream["tlsSettings"] = tls
    elif security == "reality":
        reality: dict[str, Any] = {"fingerprint": fingerprint or "chrome"}
        if sni:
            reality["serverName"] = sni
        public_key = query.get("pbk") or query.get("publicKey") or query.get("public_key") or ""
        if public_key:
            reality["password"] = public_key
        short_id = query.get("sid") or query.get("shortId") or query.get("short_id") or ""
        if short_id:
            reality["shortId"] = short_id
        spider = urllib.parse.unquote(query.get("spx") or query.get("spiderX") or "")
        if spider:
            reality["spiderX"] = spider
        stream["realitySettings"] = reality

    return {
        "protocol": "vless",
        "tag": "proxy",
        "settings": settings,
        "streamSettings": stream,
    }


def make_xray_test_config(node: Node, port: int, log_path: Path) -> dict[str, Any]:
    return {
        "log": {"loglevel": "warning", "error": str(log_path)},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "socks",
            "settings": {"udp": True, "ip": "127.0.0.1"},
            "tag": "test-in",
        }],
        "outbounds": [
            make_xray_vless_outbound(node),
            {"protocol": "freedom", "tag": "direct"},
        ],
    }


def make_test_config(node: Node, port: int, log_path: Path) -> dict[str, Any]:
    outbound = copy.deepcopy(node.outbound)
    outbound["tag"] = "proxy"
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


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise OSError("socket closed")
        data.extend(chunk)
    return bytes(data)


def socks5_connect(proxy_port: int, host: str, port: int, timeout: float = 2.5) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    sock.settimeout(timeout)
    sock.sendall(b"\x05\x01\x00")
    if _recv_exact(sock, 2) != b"\x05\x00":
        raise OSError("SOCKS auth")

    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 4:
            address_type = 1
            address = socket.inet_pton(socket.AF_INET, host)
        else:
            address_type = 4
            address = socket.inet_pton(socket.AF_INET6, host)
    except ValueError:
        encoded = host.encode("idna")
        address_type = 3
        address = bytes([len(encoded)]) + encoded

    request = b"\x05\x01\x00" + bytes([address_type]) + address + struct.pack("!H", port)
    sock.sendall(request)
    header = _recv_exact(sock, 4)
    if header[1] != 0:
        raise OSError(f"SOCKS REP={header[1]}")

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
        secure_socket.close()
        if b"204" not in data and b"200" not in data:
            return None
        return (time.perf_counter() - started) * 1000.0
    except Exception:
        try:
            if raw_socket:
                raw_socket.close()
        except Exception:
            pass
        return None


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
    control = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    control.settimeout(timeout)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(timeout)

    try:
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
        try:
            udp.close()
        except Exception:
            pass
        try:
            control.close()
        except Exception:
            pass


def _test_tcp_targets(proxy_port: int, timeout: float) -> tuple[int, int]:
    success = 0
    for host, port in TCP_CHECKS:
        try:
            sock = socks5_connect(proxy_port, host, port, timeout=timeout)
            sock.close()
            success += 1
        except Exception:
            pass
    return success, len(TCP_CHECKS)


def _apply_health_score(node: Node, https_success: int, https_ms: float | None) -> None:
    attempts = HTTPS_ATTEMPTS
    stability = https_success / attempts
    tcp_ratio = node.tcp_ok / node.tcp_total if node.tcp_total else 0.0

    score = stability * 600.0
    score += tcp_ratio * 200.0
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


def _test_node_singbox(node: Node, singbox: Path, timeout: float = 3.0) -> Node:
    port = find_free_port()
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", node.name)[:40] or "node"
    config_path = RUNTIME_DIR / f"test_{threading.get_ident()}_{port}.json"
    log_path = RUNTIME_DIR / f"test_{safe_name}_{port}.log"
    config = make_test_config(node, port, log_path)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    process: subprocess.Popen[Any] | None = None

    try:
        check = subprocess.run(
            [str(singbox), "check", "-c", str(config_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        if check.returncode != 0:
            node.valid = False
            node.error = ((check.stderr or check.stdout or "config rejected").strip())[-800:]
            node.test_status = "Конфиг не поддержан"
            return node

        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        process = subprocess.Popen(
            [str(singbox), "run", "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        if not _wait_port(port, process, 4.5):
            node.valid = False
            node.error = "sing-box не запустил тестовый прокси"
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
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
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
    port = find_free_port()
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", node.name)[:40] or "node"
    config_path = RUNTIME_DIR / f"xray_test_{threading.get_ident()}_{port}.json"
    log_path = RUNTIME_DIR / f"xray_test_{safe_name}_{port}.log"
    config = make_xray_test_config(node, port, log_path)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    process: subprocess.Popen[Any] | None = None

    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        process = subprocess.Popen(
            [str(xray), "run", "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        if not _wait_port(port, process, 5.0):
            node.valid = False
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-1000:]
            except Exception:
                tail = ""
            node.error = tail or "xray не запустил тестовый SOCKS"
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
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
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


def test_node(node: Node, singbox: Path, xray: Path | None = None, timeout: float = 3.0) -> Node:
    node.tcp_ok = 0
    node.tcp_total = 0
    node.udp_ok = False
    node.https_ms = None
    node.score = -999999.0

    if node.protocol == "vless":
        if xray is None:
            node.valid = False
            node.score = -5000.0
            node.test_status = "Нужен Xray"
            node.error = "Для VLESS XHTTP/gRPC/WS/REALITY нужен xray.exe."
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
