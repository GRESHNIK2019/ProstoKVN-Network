# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Единый слой знаний о VPN-протоколах ProstoKVN Network.

Модуль отделяет формат подписки от способа запуска ядра. UI и lifecycle-код
работают с ``Node``, а здесь решается:
- какие поля обязательны для конкретного протокола;
- какое ядро использовать;
- как собрать корректный Xray VLESS outbound;
- какие комбинации transport/security заведомо несовместимы.

Никаких сетевых процессов этот модуль не запускает.
"""

import copy
from dataclasses import dataclass
import ipaddress
import json
import re
import urllib.parse
import uuid as uuidlib
from typing import Any

from nodes import Node, _bool, _split_csv


SINGBOX_PROTOCOLS = {
    "vmess",
    "trojan",
    "shadowsocks",
    "hysteria2",
    "tuic",
}
XRAY_VLESS_TRANSPORTS = {
    "raw",
    "tcp",
    "websocket",
    "ws",
    "grpc",
    "xhttp",
    "httpupgrade",
    "http-upgrade",
    "mkcp",
    "hysteria",
}
SINGBOX_VLESS_TRANSPORTS = {
    "raw",
    "tcp",
    "websocket",
    "ws",
    "grpc",
    "httpupgrade",
    "http-upgrade",
    "http",
    "h2",
    "quic",
}

SS_METHODS = {
    "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
    "none",
    "aes-128-gcm",
    "aes-192-gcm",
    "aes-256-gcm",
    "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305",
    # legacy — sing-box всё ещё понимает их, но новые конфигурации лучше не создавать
    "aes-128-ctr",
    "aes-192-ctr",
    "aes-256-ctr",
    "aes-128-cfb",
    "aes-192-cfb",
    "aes-256-cfb",
    "rc4-md5",
    "chacha20-ietf",
    "xchacha20",
}
TUIC_CC = {"", "cubic", "new_reno", "bbr"}
TUIC_UDP_MODE = {"", "native", "quic"}


@dataclass(frozen=True)
class ProtocolIssue:
    level: str  # error | warning
    code: str
    message: str


@dataclass(frozen=True)
class EnginePlan:
    engine: str  # sing-box | xray
    reason: str
    requires_xray: bool = False


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except Exception:
        return False


def _transport(node: Node) -> str:
    value = str(node.extra.get("transport") or "").strip().lower()
    if value:
        return value
    outbound = node.outbound if isinstance(node.outbound, dict) else {}
    tr = outbound.get("transport")
    if isinstance(tr, dict):
        return str(tr.get("type") or "raw").strip().lower()
    return "raw"


def _security(node: Node) -> str:
    value = str(node.extra.get("security") or "").strip().lower()
    if value:
        return value
    tls = node.outbound.get("tls") if isinstance(node.outbound, dict) else None
    if isinstance(tls, dict) and _bool(tls.get("enabled", True)):
        reality = tls.get("reality")
        if isinstance(reality, dict) and _bool(reality.get("enabled", True)):
            return "reality"
        return "tls"
    return "none"


def _valid_uuid(value: object) -> bool:
    try:
        uuidlib.UUID(str(value or ""))
        return True
    except Exception:
        return False


def _private_destination(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except Exception:
        name = host.rstrip(".").lower()
        return name in {"localhost"} or name.endswith((".local", ".lan", ".internal"))


def validate_node(node: Node) -> list[ProtocolIssue]:
    """Проверяет протокол до запуска внешнего ядра.

    Проверка намеренно не пытается «чинить» секреты или транспорт: неверный
    параметр лучше показать как понятную ошибку, чем молча подключиться иначе.
    """
    issues: list[ProtocolIssue] = []
    protocol = str(node.protocol or "").strip().lower()

    if not node.server:
        issues.append(ProtocolIssue("error", "server.empty", "Не указан адрес сервера."))
    if not (1 <= int(node.port or 0) <= 65535):
        issues.append(ProtocolIssue("error", "port.invalid", "Порт должен быть в диапазоне 1..65535."))

    outbound = node.outbound if isinstance(node.outbound, dict) else {}
    transport = _transport(node)
    security = _security(node)

    if protocol == "vless":
        if not _valid_uuid(outbound.get("uuid")):
            issues.append(ProtocolIssue("error", "vless.uuid", "VLESS требует корректный UUID."))
        if transport not in XRAY_VLESS_TRANSPORTS | SINGBOX_VLESS_TRANSPORTS:
            issues.append(ProtocolIssue("error", "vless.transport", f"Неизвестный VLESS transport: {transport}."))

        flow = str(outbound.get("flow") or "").strip()
        if flow and flow not in {"xtls-rprx-vision", "xtls-rprx-vision-udp443"}:
            issues.append(ProtocolIssue("warning", "vless.flow.unknown", f"Неизвестный VLESS flow: {flow}."))
        if flow and transport not in {"raw", "tcp"}:
            issues.append(ProtocolIssue(
                "error",
                "vless.vision.transport",
                "XTLS Vision совместим с обычным TCP/RAW + TLS/REALITY, но не с этим transport.",
            ))
        if flow and security not in {"tls", "reality"}:
            issues.append(ProtocolIssue(
                "error",
                "vless.vision.security",
                "XTLS Vision требует TLS или REALITY.",
            ))

        encryption = str(_node_query(node).get("encryption") or "none").strip().lower()
        if security == "none" and encryption in {"", "none"} and not _private_destination(node.server):
            issues.append(ProtocolIssue(
                "warning",
                "vless.public.no_security",
                "Публичный VLESS без TLS/REALITY или VLESS Encryption не рекомендуется.",
            ))

        if security == "reality":
            query = _node_query(node)
            if not (query.get("pbk") or query.get("publicKey") or query.get("public_key")):
                issues.append(ProtocolIssue("error", "reality.public_key", "REALITY требует public key (pbk)."))

    elif protocol == "vmess":
        if not _valid_uuid(outbound.get("uuid")):
            issues.append(ProtocolIssue("error", "vmess.uuid", "VMess требует корректный UUID."))

    elif protocol == "trojan":
        if not str(outbound.get("password") or ""):
            issues.append(ProtocolIssue("error", "trojan.password", "Trojan требует пароль."))
        if security == "none":
            issues.append(ProtocolIssue(
                "warning",
                "trojan.no_tls",
                "Trojan обычно должен использовать TLS; проверь параметры подписки.",
            ))

    elif protocol == "shadowsocks":
        method = str(outbound.get("method") or "").strip().lower()
        if method not in SS_METHODS:
            issues.append(ProtocolIssue("error", "ss.method", f"Метод Shadowsocks не поддерживается: {method or 'не задан'}."))
        if method != "none" and not str(outbound.get("password") or ""):
            issues.append(ProtocolIssue("error", "ss.password", "Shadowsocks требует пароль."))

    elif protocol == "hysteria2":
        if not str(outbound.get("password") or ""):
            issues.append(ProtocolIssue("error", "hy2.password", "Hysteria2 требует пароль."))
        tls = outbound.get("tls")
        if not isinstance(tls, dict) or not _bool(tls.get("enabled", True)):
            issues.append(ProtocolIssue("error", "hy2.tls", "Hysteria2 требует TLS."))
        obfs = outbound.get("obfs")
        if isinstance(obfs, dict):
            obfs_type = str(obfs.get("type") or "").strip().lower()
            if obfs_type and obfs_type not in {"salamander"}:
                issues.append(ProtocolIssue(
                    "error",
                    "hy2.obfs.version",
                    f"obfs={obfs_type} требует более нового sing-box; проверенная ветка использует salamander.",
                ))
            if obfs_type and not str(obfs.get("password") or ""):
                issues.append(ProtocolIssue("error", "hy2.obfs.password", "Hysteria2 obfs требует пароль."))

    elif protocol == "tuic":
        if not _valid_uuid(outbound.get("uuid")):
            issues.append(ProtocolIssue("error", "tuic.uuid", "TUIC требует корректный UUID."))
        if not str(outbound.get("password") or ""):
            issues.append(ProtocolIssue("error", "tuic.password", "TUIC требует пароль."))
        cc = str(outbound.get("congestion_control") or "").strip().lower()
        if cc not in TUIC_CC:
            issues.append(ProtocolIssue("error", "tuic.cc", f"Неизвестный congestion_control: {cc}."))
        relay = str(outbound.get("udp_relay_mode") or "").strip().lower()
        if relay not in TUIC_UDP_MODE:
            issues.append(ProtocolIssue("error", "tuic.udp_mode", f"Неизвестный udp_relay_mode: {relay}."))
        if _bool(outbound.get("zero_rtt_handshake")):
            issues.append(ProtocolIssue(
                "warning",
                "tuic.0rtt",
                "TUIC 0-RTT отключать безопаснее: режим подвержен replay-атакам.",
            ))
        tls = outbound.get("tls")
        if not isinstance(tls, dict) or not _bool(tls.get("enabled", True)):
            issues.append(ProtocolIssue("error", "tuic.tls", "TUIC требует TLS."))

    else:
        issues.append(ProtocolIssue("error", "protocol.unsupported", f"Протокол {protocol or '—'} не поддерживается."))

    return issues


def fatal_issues(node: Node) -> list[ProtocolIssue]:
    return [issue for issue in validate_node(node) if issue.level == "error"]


def choose_engine(node: Node, *, xray_available: bool = True) -> EnginePlan:
    protocol = str(node.protocol or "").lower()
    if protocol == "vless":
        transport = _transport(node)
        if transport == "xhttp":
            return EnginePlan("xray", "XHTTP реализуется через Xray-core.", requires_xray=True)
        # В текущей ветке VLESS по умолчанию оставляем на Xray: это сохраняет
        # поведение уже проверенных WS/gRPC/REALITY подписок. Архитектура при этом
        # знает, какие transport можно позднее безопасно переключить на sing-box.
        if xray_available:
            return EnginePlan("xray", "VLESS запускается через совместимый Xray bridge.", requires_xray=True)
        if transport in SINGBOX_VLESS_TRANSPORTS:
            return EnginePlan("sing-box", "Xray недоступен, transport поддерживается sing-box.")
        return EnginePlan("xray", f"VLESS {transport} требует Xray-core.", requires_xray=True)

    if protocol in SINGBOX_PROTOCOLS:
        return EnginePlan("sing-box", f"{protocol} поддерживается sing-box напрямую.")
    return EnginePlan("sing-box", "Протокол передаётся sing-box.")


def singbox_outbound(node: Node) -> dict[str, Any]:
    """Возвращает outbound без мутации исходного Node."""
    outbound = copy.deepcopy(node.outbound)
    outbound["tag"] = "proxy"
    return outbound


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
    query = node.extra.get("query")
    if isinstance(query, dict) and query:
        return {str(key): str(value) for key, value in query.items()}

    if node.source.lower().startswith("vless://"):
        parsed = urllib.parse.urlsplit(node.source)
        values = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        return {key: (items[0] if items else "") for key, items in values.items()}

    result: dict[str, str] = {}
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

    clash = node.extra.get("clash")
    if isinstance(clash, dict):
        network = str(clash.get("network") or result.get("type") or "raw").lower()
        result["type"] = network
        reality_opts = clash.get("reality-opts") or clash.get("reality_opts")
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
    """Строит Xray VLESS outbound в совместимой схеме network/publicKey.

    Мы сознательно используем традиционные поля ``network`` и ``publicKey``.
    Они работают и на старых установленных Xray, и на актуальной ветке, поэтому
    больше не нужен runtime monkey-patch из ``xray_compat.py``.
    """
    if node.protocol != "vless":
        raise ValueError("Xray builder используется только для VLESS")

    query = _node_query(node)
    settings: dict[str, Any] = {
        "address": node.server,
        "port": node.port,
        "id": str(node.outbound.get("uuid") or ""),
        "encryption": query.get("encryption", "none") or "none",
    }
    flow = str(node.outbound.get("flow") or query.get("flow") or "")
    if flow:
        settings["flow"] = flow

    transport = str(node.extra.get("transport") or query.get("type") or query.get("network") or "raw").lower()
    network_map = {
        "tcp": "raw",
        "raw": "raw",
        "ws": "websocket",
        "websocket": "websocket",
        "grpc": "grpc",
        "xhttp": "xhttp",
        "httpupgrade": "httpupgrade",
        "http-upgrade": "httpupgrade",
    }
    network = network_map.get(transport, transport if transport in XRAY_VLESS_TRANSPORTS else "raw")
    security = str(node.extra.get("security") or query.get("security") or "none").lower()
    stream: dict[str, Any] = {"network": network, "security": security}

    path = urllib.parse.unquote(query.get("path", ""))
    host = urllib.parse.unquote(query.get("host", ""))
    if network == "websocket":
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
    elif network == "grpc":
        service = urllib.parse.unquote(query.get("serviceName") or query.get("service_name") or query.get("service-name") or path or "")
        grpc: dict[str, Any] = {}
        if service:
            grpc["serviceName"] = service
        if query.get("authority"):
            grpc["authority"] = urllib.parse.unquote(query["authority"])
        stream["grpcSettings"] = grpc
    elif network == "xhttp":
        xhttp: dict[str, Any] = {}
        if path:
            xhttp["path"] = path
        if host:
            xhttp["host"] = host
        if query.get("mode"):
            xhttp["mode"] = query["mode"]
        extra_raw = urllib.parse.unquote(query.get("extra", ""))
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
                if isinstance(extra, dict):
                    xhttp["extra"] = extra
            except Exception:
                pass
        stream["xhttpSettings"] = xhttp
    elif network == "httpupgrade":
        upgrade: dict[str, Any] = {}
        if path:
            upgrade["path"] = path
        if host:
            upgrade["host"] = host
        stream["httpupgradeSettings"] = upgrade

    sni = urllib.parse.unquote(query.get("sni") or query.get("serverName") or query.get("servername") or "")
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
            reality["publicKey"] = public_key
        short_id = query.get("sid") or query.get("shortId") or query.get("short_id") or ""
        if short_id:
            reality["shortId"] = short_id
        spider = urllib.parse.unquote(query.get("spx") or query.get("spiderX") or "")
        if spider:
            reality["spiderX"] = spider
        stream["realitySettings"] = reality

    return {"protocol": "vless", "tag": "proxy", "settings": settings, "streamSettings": stream}


def make_xray_test_config(node: Node, port: int, log_path: Any) -> dict[str, Any]:
    return {
        "log": {"loglevel": "warning", "error": str(log_path)},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "socks",
            "settings": {"udp": True, "ip": "127.0.0.1"},
            "tag": "test-in",
        }],
        "outbounds": [make_xray_vless_outbound(node), {"protocol": "freedom", "tag": "direct"}],
    }


def protocol_summary_label(node: Node) -> str:
    plan = choose_engine(node, xray_available=True)
    return f"{node.stack_label()} · {plan.engine}"
