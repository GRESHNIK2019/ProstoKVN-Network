# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

from node_tester import find_free_port, make_xray_test_config, _wait_port
from nodes import Node
from paths import RUNTIME_DIR
from routing import make_tun_config, normalize_process_names


# Одновременно запускаем или останавливаем только один VPN-сеанс.
# Это защищает от гонки при быстрых переключениях стратегии.
_VPN_LIFECYCLE_LOCK = threading.RLock()
TUN_INTERFACE_NAME = "prostokvn_network_tun"


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


def _process_alive(process: subprocess.Popen[Any] | None) -> bool:
    return bool(process and process.poll() is None)


def _stop_process_tree(process: subprocess.Popen[Any] | None) -> None:
    if not _process_alive(process):
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=6,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    else:
        try:
            process.terminate()
            process.wait(timeout=4)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    try:
        process.wait(timeout=2)
    except Exception:
        pass


def _kill_stale_runtime_processes(config_paths: list[Path]) -> None:
    """Убирает только старые процессы, запущенные с нашими runtime-конфигами."""
    if os.name != "nt":
        return

    needles = [str(path.resolve()).lower() for path in config_paths]
    if not needles:
        return

    quoted = ",".join("'" + item.replace("'", "''") + "'" for item in needles)
    script = (
        f"$needles=@({quoted}); "
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "$cmd=[string]$_.CommandLine; "
        "if (-not $cmd) { return }; "
        "$lower=$cmd.ToLowerInvariant(); "
        "$match=$false; "
        "foreach ($needle in $needles) { if ($lower.Contains($needle)) { $match=$true; break } }; "
        "if ($match) { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } "
        "}"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def _wait_tun_interface(
    name: str,
    process: subprocess.Popen[Any] | None,
    xray_process: subprocess.Popen[Any] | None = None,
    require_xray: bool = False,
    timeout: float = 8.0,
) -> bool:
    """Ждёт реального появления TUN, а не только живого процесса sing-box."""
    end = time.time() + max(0.0, timeout)
    while time.time() < end:
        if not _process_alive(process):
            return False
        if require_xray and not _process_alive(xray_process):
            return False
        if _interface_probably_exists(name):
            return True
        time.sleep(0.25)

    # Последняя проверка закрывает гонку, когда интерфейс появился на границе
    # таймаута между последней итерацией и выходом из цикла.
    return (
        _process_alive(process)
        and (not require_xray or _process_alive(xray_process))
        and _interface_probably_exists(name)
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
        self._starting = False
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
        with _VPN_LIFECYCLE_LOCK:
            if self._main_process_running():
                return

            self._starting = True
            try:
                # После аварийного завершения прошлой копии могли остаться процессы,
                # которые всё ещё используют наши active_*.json.
                _kill_stale_runtime_processes([self.cfg_path, self.xray_cfg_path])
                self._prepare_runtime_files()

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
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if check.returncode != 0:
                    details = (check.stderr or check.stdout or "").strip()[-1600:]
                    raise RuntimeError("sing-box отклонил рабочий конфиг:\n" + details)

                self.proc = subprocess.Popen(
                    [str(self.singbox), "run", "-c", str(self.cfg_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_creation_flags(),
                )

                ready = _wait_tun_interface(
                    TUN_INTERFACE_NAME,
                    self.proc,
                    self.xray_proc,
                    require_xray=(self.node.protocol == "vless"),
                    timeout=8.0,
                )
                if ready:
                    return

                if self.proc.poll() is not None:
                    raise RuntimeError("TUN завершился при запуске:\n" + self.failure_reason())
                if self.node.protocol == "vless" and not _process_alive(self.xray_proc):
                    raise RuntimeError("Xray завершился при запуске:\n" + self.failure_reason())

                # Раньше живой sing-box после истечения таймаута считался успешным
                # запуском даже без созданного TUN-интерфейса.
                raise RuntimeError(
                    f"TUN-интерфейс {TUN_INTERFACE_NAME} не появился за 8 секунд.\n"
                    + self.failure_reason()
                )
            except Exception:
                self._stop_locked()
                raise
            finally:
                self._starting = False

    def stop(self) -> None:
        with _VPN_LIFECYCLE_LOCK:
            self._starting = False
            self._stop_locked()

    def _stop_locked(self) -> None:
        # Сначала TUN, затем локальный Xray-мост.
        _stop_process_tree(self.proc)
        _stop_process_tree(self.xray_proc)

        self.proc = None
        self.xray_proc = None
        for path in (self.cfg_path, self.xray_cfg_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def _prepare_runtime_files(self) -> None:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        for path in (self.cfg_path, self.xray_cfg_path, self.log_path, self.xray_log_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def _main_process_running(self) -> bool:
        if not _process_alive(self.proc):
            return False
        if self.node.protocol == "vless":
            return _process_alive(self.xray_proc)
        return True

    def running(self) -> bool:
        # Watchdog не должен считать VPN упавшим, пока start() ещё поднимает Xray/TUN.
        if self._starting:
            return True
        return self._main_process_running()

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
