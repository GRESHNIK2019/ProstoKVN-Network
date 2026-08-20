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

from external_process import run_external
from node_tester import find_free_port, _wait_port
from nodes import Node
from paths import RUNTIME_DIR
from process_manager import PROCESS_MANAGER, process_alive
from protocol_engine import choose_engine, fatal_issues, make_xray_test_config
from routing import make_tun_config, normalize_process_names


_VPN_LIFECYCLE_LOCK = threading.RLock()
TUN_INTERFACE_NAME = "prostokvn_network_tun"
TUN_INTERFACE_IPV4 = "172.29.77.1"
TUN_START_TIMEOUT = 12.0


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _wait_tun_interface(
    name: str,
    process: subprocess.Popen[Any] | None,
    xray_process: subprocess.Popen[Any] | None = None,
    require_xray: bool = False,
    timeout: float = TUN_START_TIMEOUT,
) -> bool:
    end = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < end:
        if not process_alive(process):
            return False
        if require_xray and not process_alive(xray_process):
            return False
        if _interface_probably_exists(name):
            return True
        time.sleep(0.25)
    return (
        process_alive(process)
        and (not require_xray or process_alive(xray_process))
        and _interface_probably_exists(name)
    )


class TunRunner:
    """Один атомарный VPN-сеанс."""

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
        self.singbox = Path(singbox)
        self.xray = Path(xray) if xray else None
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
        self._health_stop: threading.Event | None = None
        self._health_thread: threading.Thread | None = None
        self._health_failure = ""
        self._plan = choose_engine(node, xray_available=self.xray is not None)

        self.cfg_path = RUNTIME_DIR / "active_tun.json"
        self.log_path = RUNTIME_DIR / "active_tun.log"
        self.xray_cfg_path = RUNTIME_DIR / "active_xray.json"
        self.xray_log_path = RUNTIME_DIR / "active_xray.log"

    def _validate(self) -> None:
        errors = fatal_issues(self.node)
        if errors:
            raise RuntimeError("Профиль узла некорректен:\n" + "\n".join(f"• {item.message}" for item in errors))
        if not self.singbox.is_file():
            raise RuntimeError("Не найден sing-box.exe")
        if self._plan.requires_xray and (self.xray is None or not self.xray.is_file()):
            raise RuntimeError("Для выбранного VLESS-профиля нужен совместимый xray.exe")

    def _start_xray_bridge(self) -> dict[str, Any]:
        if not self.xray:
            raise RuntimeError("Для выбранного VLESS-узла нужен xray.exe")

        port = find_free_port()
        config = make_xray_test_config(self.node, port, self.xray_log_path)
        self.xray_cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.xray_proc = PROCESS_MANAGER.spawn(
            [str(self.xray), "run", "-c", str(self.xray_cfg_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_port(port, self.xray_proc, 7.0):
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
            self._health_failure = ""
            self._health_stop = threading.Event()
            try:
                self._validate()
                PROCESS_MANAGER.cleanup_owned_processes(RUNTIME_DIR, tests_only=False)
                self._prepare_runtime_files()

                proxy_override = None
                if self._plan.engine == "xray":
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
                self.cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

                check = run_external(
                    [str(self.singbox), "check", "-c", str(self.cfg_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if check.returncode != 0:
                    details = (check.stderr or check.stdout or "").strip()[-1800:]
                    raise RuntimeError("sing-box отклонил рабочий конфиг:\n" + details)

                self.proc = PROCESS_MANAGER.spawn(
                    [str(self.singbox), "run", "-c", str(self.cfg_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                require_xray = self._plan.engine == "xray"
                ready = _wait_tun_interface(
                    TUN_INTERFACE_NAME,
                    self.proc,
                    self.xray_proc,
                    require_xray=require_xray,
                    timeout=TUN_START_TIMEOUT,
                )
                if ready:
                    self._start_health_monitor()
                    return

                if not process_alive(self.proc):
                    raise RuntimeError("TUN завершился при запуске:\n" + self.failure_reason())
                if require_xray and not process_alive(self.xray_proc):
                    raise RuntimeError("Xray завершился при запуске:\n" + self.failure_reason())
                raise RuntimeError(
                    f"TUN-интерфейс {TUN_INTERFACE_NAME} не появился за {int(TUN_START_TIMEOUT)} секунд.\n"
                    + self.failure_reason()
                )
            except Exception:
                self._stop_locked()
                raise
            finally:
                self._starting = False

    def _start_health_monitor(self) -> None:
        stop_event = self._health_stop
        if stop_event is None:
            return

        def monitor() -> None:
            missing_checks = 0
            while not stop_event.wait(1.5):
                if not self._main_process_running():
                    return
                if _interface_probably_exists(TUN_INTERFACE_NAME):
                    missing_checks = 0
                    continue
                missing_checks += 1
                if missing_checks < 3:
                    continue
                with _VPN_LIFECYCLE_LOCK:
                    if stop_event is not self._health_stop or stop_event.is_set():
                        return
                    self._health_failure = (
                        f"TUN-интерфейс {TUN_INTERFACE_NAME} отсутствует три проверки подряд. "
                        "VPN-сеанс остановлен перед переподключением."
                    )
                    self._stop_locked()
                return

        self._health_thread = threading.Thread(target=monitor, name="ProstoKVN-TUN-Health", daemon=True)
        self._health_thread.start()

    def stop(self) -> None:
        with _VPN_LIFECYCLE_LOCK:
            self._starting = False
            self._stop_locked()

    def _stop_locked(self) -> None:
        if self._health_stop is not None:
            self._health_stop.set()
        PROCESS_MANAGER.stop(self.proc)
        PROCESS_MANAGER.stop(self.xray_proc)
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
        if not process_alive(self.proc):
            return False
        if self._plan.engine == "xray":
            return process_alive(self.xray_proc)
        return True

    def running(self) -> bool:
        if self._starting:
            return True
        if self._health_failure:
            return False
        return self._main_process_running()

    def failure_reason(self) -> str:
        parts: list[str] = []
        if self._health_failure:
            parts.append(self._health_failure)
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


def _interface_probably_exists(name: str, ipv4: str = TUN_INTERFACE_IPV4) -> bool:
    """Проверяет готовность TUN по имени И по назначенному адресу.

    На части Windows/Wintun сборок `Get-NetAdapter -Name` не всегда возвращает
    интерфейс под тем же alias, который передан sing-box в `interface_name`.
    При этом адрес из TUN-конфига уже назначен и трафик реально идёт. Поэтому
    имя адаптера используется как первый сигнал, а IPv4 — как независимый
    второй сигнал готовности. Это устраняет ложный timeout при рабочем TUN.
    """
    if os.name != "nt":
        return True

    safe_name = str(name).replace("'", "''")
    safe_ip = str(ipv4).replace("'", "''")
    script = (
        f"$n='{safe_name}'; $ip='{safe_ip}'; $ready=$false; "
        "$a=Get-NetAdapter -Name $n -ErrorAction SilentlyContinue; "
        "if ($a) {$ready=$true}; "
        "if (-not $ready) {"
        "$p=Get-NetIPAddress -IPAddress $ip -AddressFamily IPv4 -ErrorAction SilentlyContinue; "
        "if ($p) {$ready=$true}}; "
        "if (-not $ready) {"
        "$c=Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object {"
        "$_.InterfaceAlias -eq $n -or ($_.IPv4Address -and $_.IPv4Address.IPAddress -eq $ip)} | Select-Object -First 1; "
        "if ($c) {$ready=$true}}; "
        "if ($ready) {Write-Output 'READY'}"
    )
    try:
        result = run_external(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=3.0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0 and "READY" in (result.stdout or ""):
            return True
    except Exception:
        pass

    # Последний резерв без PowerShell cmdlets: netsh обычно видит уже
    # назначенный адрес даже в момент, когда Get-NetAdapter ещё не обновился.
    try:
        result = run_external(
            ["netsh", "interface", "ipv4", "show", "addresses"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (result.stdout or "").casefold()
        return safe_name.casefold() in output or safe_ip.casefold() in output
    except Exception:
        return False
