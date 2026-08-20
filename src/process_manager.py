# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Жизненный цикл внешних VPN-ядер.

Все xray/sing-box, запущенные новой сетевой частью, проходят через один менеджер.
На Windows каждый процесс добавляется в Job Object с KILL_ON_JOB_CLOSE, поэтому
он не может пережить аварийное завершение GUI. Штатный stop дополнительно убивает
дерево процесса через taskkill и ждёт фактического завершения.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading
from typing import Any, Iterable


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def windows_creation_flags() -> int:
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def process_alive(process: subprocess.Popen[Any] | None) -> bool:
    return bool(process and process.poll() is None)


class ProcessManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._children: dict[int, subprocess.Popen[Any]] = {}
        self._job: int | None = None
        self._job_ready = self._create_job()

    def _create_job(self) -> bool:
        if os.name != "nt":
            return False
        try:
            k32 = ctypes.windll.kernel32
            k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            k32.SetInformationJobObject.restype = wintypes.BOOL
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            k32.CloseHandle.restype = wintypes.BOOL

            handle = k32.CreateJobObjectW(None, None)
            if not handle:
                return False
            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = k32.SetInformationJobObject(
                handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok:
                k32.CloseHandle(handle)
                return False
            self._job = int(handle)
            return True
        except Exception:
            self._job = None
            return False

    @property
    def job_ready(self) -> bool:
        return bool(self._job_ready and self._job)

    def _assign_to_job(self, process: subprocess.Popen[Any]) -> None:
        if os.name != "nt" or not self._job:
            return
        try:
            k32 = ctypes.windll.kernel32
            k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            k32.AssignProcessToJobObject.restype = wintypes.BOOL
            raw_handle = getattr(process, "_handle", None)
            if raw_handle:
                k32.AssignProcessToJobObject(wintypes.HANDLE(self._job), wintypes.HANDLE(int(raw_handle)))
        except Exception:
            # Штатный stop и orphan cleanup остаются резервным механизмом.
            pass

    def spawn(self, args: Iterable[str] | list[str], **kwargs: Any) -> subprocess.Popen[Any]:
        if os.name == "nt" and "creationflags" not in kwargs:
            kwargs["creationflags"] = windows_creation_flags()
        process = subprocess.Popen(list(args), **kwargs)
        self._assign_to_job(process)
        with self._lock:
            self._children[int(process.pid)] = process
        return process

    def forget(self, process: subprocess.Popen[Any] | None) -> None:
        if process is None:
            return
        with self._lock:
            self._children.pop(int(process.pid), None)

    def stop(self, process: subprocess.Popen[Any] | None, timeout: float = 6.0) -> None:
        if process is None:
            return
        if process.poll() is not None:
            self.forget(process)
            return

        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=max(1.0, timeout),
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
            except Exception:
                pass

        try:
            process.wait(timeout=max(0.5, min(timeout, 3.0)))
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
            try:
                process.wait(timeout=1.0)
            except Exception:
                pass
        self.forget(process)

    def stop_all(self) -> None:
        with self._lock:
            children = list(self._children.values())
        for process in children:
            self.stop(process)

    def close(self) -> None:
        self.stop_all()
        handle = self._job
        self._job = None
        self._job_ready = False
        if os.name == "nt" and handle:
            try:
                ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(handle))
            except Exception:
                pass

    @staticmethod
    def cleanup_owned_processes(runtime_dir: Path, *, tests_only: bool = False) -> int:
        """Убивает orphan xray/sing-box только от ProstoKVN Network.

        Совпадение идёт по command line с постоянным runtime-каталогом приложения
        или по legacy `_MEI...\\runtime` из старых сборок. Имена процессов других
        клиентов не трогаются без совпадения с нашими конфигами.
        """
        if os.name != "nt":
            return 0

        runtime = str(runtime_dir.resolve()).lower().replace("'", "''")
        test_clause = (
            "$known=$lower.Contains('xray_test_') -or $lower.Contains('test_'); "
            if tests_only
            else "$known=$lower.Contains('active_tun.json') -or $lower.Contains('active_xray.json') -or $lower.Contains('xray_test_') -or $lower.Contains('test_'); "
        )
        script = (
            f"$runtime='{runtime}'; $count=0; "
            "$names=@('xray.exe','sing-box.exe','sing-box-client.exe'); "
            "Get-CimInstance Win32_Process | ForEach-Object { "
            "$name=([string]$_.Name).ToLowerInvariant(); "
            "if ($names -notcontains $name) { return }; "
            "$cmd=[string]$_.CommandLine; if (-not $cmd) { return }; "
            "$lower=$cmd.ToLowerInvariant(); "
            + test_clause +
            "$owned=$known -and $lower.Contains($runtime); "
            "if (-not $owned) { "
            "$legacy=$known -and $lower.Contains('\\appdata\\local\\temp\\_mei') -and $lower.Contains('\\runtime\\'); "
            "$owned=$legacy }; "
            "if ($owned) { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $count++ } "
            "}; Write-Output $count"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                return 0
            lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
            return int(lines[-1]) if lines else 0
        except Exception:
            return 0


PROCESS_MANAGER = ProcessManager()
