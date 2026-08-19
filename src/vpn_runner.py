# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from node_tester import find_free_port, make_xray_test_config, _wait_port
from nodes import Node
from paths import RUNTIME_DIR
from routing import make_tun_config, normalize_process_names


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


class TunRunner:
    def __init__(
        self,
        singbox: Path,
        node: Node,
        discord_vpn: bool = True,
        steam_webhelper_vpn: bool = False,
        xray: Path | None = None,
        blocked_ru_vpn: bool = True,
        blocklist_paths: list[Path] | None = None,
        route_mode: str = "smart_ru",
        custom_vpn_processes: list[str] | None = None,
    ):
        self.singbox = singbox
        self.xray = xray
        self.node = node
        self.discord_vpn = discord_vpn
        self.steam_webhelper_vpn = steam_webhelper_vpn
        self.blocked_ru_vpn = blocked_ru_vpn
        self.route_mode = route_mode
        self.custom_vpn_processes = normalize_process_names(custom_vpn_processes or [])
        self.blocklist_paths = list(blocklist_paths or [])

        self.proc: subprocess.Popen[Any] | None = None
        self.xray_proc: subprocess.Popen[Any] | None = None
        self.cfg_path = RUNTIME_DIR / "active_tun.json"
        self.log_path = RUNTIME_DIR / "active_tun.log"
        self.xray_cfg_path = RUNTIME_DIR / "active_xray.json"
        self.xray_log_path = RUNTIME_DIR / "active_xray.log"

    def _start_xray_bridge(self) -> dict[str, Any]:
        if not self.xray:
            raise RuntimeError("Для выбранного VLESS-узла нужен xray.exe")

        port = find_free_port()
        config = make_xray_test_config(self.node, port, self.xray_log_path)
        self.xray_cfg_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.xray_proc = subprocess.Popen(
            [str(self.xray), "run", "-c", str(self.xray_cfg_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creation_flags(),
        )

        if not _wait_port(port, self.xray_proc, 6.0):
            raise RuntimeError(
                "Xray не смог поднять выбранный VLESS-узел:\n" + self._read_log_tail(self.xray_log_path)
            )

        return {
            "type": "socks",
            "tag": "proxy",
            "server": "127.0.0.1",
            "server_port": port,
            "version": "5",
        }

    def start(self) -> None:
        if self.running():
            return

        proxy_override = None
        if self.node.protocol == "vless":
            proxy_override = self._start_xray_bridge()

        config = make_tun_config(
            self.node,
            self.log_path,
            discord_vpn=self.discord_vpn,
            steam_webhelper_vpn=self.steam_webhelper_vpn,
            blocked_ru_vpn=self.blocked_ru_vpn,
            blocklist_paths=self.blocklist_paths,
            proxy_override=proxy_override,
            route_mode=self.route_mode,
            custom_vpn_processes=self.custom_vpn_processes,
        )
        self.cfg_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        check = subprocess.run(
            [str(self.singbox), "check", "-c", str(self.cfg_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if check.returncode != 0:
            self.stop()
            details = (check.stderr or check.stdout or "").strip()[-1600:]
            raise RuntimeError("sing-box отклонил рабочий конфиг:\n" + details)

        self.proc = subprocess.Popen(
            [str(self.singbox), "run", "-c", str(self.cfg_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creation_flags(),
        )

        end = time.time() + 8
        while time.time() < end:
            if self.proc.poll() is not None:
                reason = self.failure_reason()
                self.stop()
                raise RuntimeError("TUN завершился при запуске:\n" + reason)
            if _interface_probably_exists("prostokvn_network_tun"):
                return
            time.sleep(0.25)

        if self.proc.poll() is not None:
            reason = self.failure_reason()
            self.stop()
            raise RuntimeError("TUN не запустился:\n" + reason)

    def stop(self) -> None:
        for process in (self.proc, self.xray_proc):
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=4)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

        self.proc = None
        self.xray_proc = None
        for path in (self.cfg_path, self.xray_cfg_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def failure_reason(self) -> str:
        parts: list[str] = []
        tun_log = self._read_log_tail(self.log_path)
        xray_log = self._read_log_tail(self.xray_log_path)
        if tun_log:
            parts.append(tun_log)
        if xray_log:
            parts.append(xray_log)
        return "\n".join(parts).strip() or "процесс VPN завершился без подробностей"

    @staticmethod
    def _read_log_tail(path: Path, limit: int = 2500) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[-limit:].strip()
        except Exception:
            return ""


def _interface_probably_exists(name: str) -> bool:
    if os.name != "nt":
        return True
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetAdapter -Name '{name}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return name.lower() in (result.stdout or "").lower()
    except Exception:
        return False
