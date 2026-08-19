# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading


# Windows Job Object с этим флагом гарантирует, что дочерние xray/sing-box
# не переживут завершение ProstoKVN Network, даже если приложение аварийно
# закроется во время запуска/проверки узла.
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

_JOB_HANDLE: int | None = None
_JOB_LOCK = threading.Lock()


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
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


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def install_kill_on_exit_job() -> bool:
    """Привязывает текущий процесс и его будущих детей к Job Object.

    Handle намеренно хранится до завершения процесса. Когда ProstoKVN Network
    закрывается, Windows закрывает последний handle Job Object и автоматически
    завершает оставшиеся дочерние процессы.
    """
    global _JOB_HANDLE

    if os.name != "nt":
        return False

    with _JOB_LOCK:
        if _JOB_HANDLE:
            return True

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return False

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        if not kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(handle)
            return False

        if not kernel32.AssignProcessToJobObject(handle, kernel32.GetCurrentProcess()):
            # На части окружений процесс уже находится в несовместимом Job Object.
            # В этом случае штатный stop/cleanup остаётся резервным механизмом.
            kernel32.CloseHandle(handle)
            return False

        _JOB_HANDLE = int(handle)
        return True


def cleanup_stale_core_processes(runtime_dir: Path) -> int:
    """Удаляет только оставшиеся xray/sing-box именно от ProstoKVN Network.

    Помимо нового постоянного runtime-каталога распознаётся старый путь PyInstaller
    `_MEI...\\runtime`, чтобы один раз убрать процессы от предыдущих тестовых сборок.
    Процессы v2rayN и других программ не затрагиваются.
    """
    if os.name != "nt":
        return 0

    runtime = str(runtime_dir.resolve()).lower().replace("'", "''")
    script = (
        f"$runtime='{runtime}'; $count=0; "
        "$names=@('xray.exe','sing-box.exe','sing-box-client.exe'); "
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "$name=([string]$_.Name).ToLowerInvariant(); "
        "if ($names -notcontains $name) { return }; "
        "$cmd=[string]$_.CommandLine; if (-not $cmd) { return }; "
        "$lower=$cmd.ToLowerInvariant(); "
        "$owned=$lower.Contains($runtime); "
        "if (-not $owned) { "
        "$legacy=$lower.Contains('\\appdata\\local\\temp\\_mei') -and $lower.Contains('\\runtime\\'); "
        "$known=$lower.Contains('active_tun.json') -or $lower.Contains('active_xray.json') -or "
        "$lower.Contains('xray_test_') -or $lower.Contains('test_'); "
        "$owned=$legacy -and $known }; "
        "if ($owned) { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $count++ } "
        "}; Write-Output $count"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return 0
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        return int(lines[-1]) if lines else 0
    except Exception:
        return 0
