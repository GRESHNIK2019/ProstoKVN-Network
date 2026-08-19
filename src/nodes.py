# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field
import ipaddress
import json
import re
from typing import Any, Callable
import urllib.parse
import urllib.request

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

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


