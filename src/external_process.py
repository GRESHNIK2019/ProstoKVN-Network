# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Безопасный запуск внешних Windows-программ из frozen PyInstaller.

В onefile-сборке PyInstaller на Windows меняет DLL search directory на
``sys._MEIPASS`` через SetDllDirectoryW. Это значение наследуется дочерними
процессами. Если внешний xray/sing-box/PowerShell случайно загрузит DLL из
``_MEI...``, Windows будет держать файл открытым и bootloader не сможет удалить
временный каталог при выходе.

Все внешние процессы ProstoKVN запускаются через этот модуль. На короткий момент
создания дочернего процесса стандартный DLL search path восстанавливается, а
после ``Popen`` исходное значение возвращается приложению. Операция защищена
общим lock, потому что SetDllDirectoryW действует на весь процесс.
"""

import ctypes
import os
import subprocess
import sys
import threading
from typing import Any, Iterable


_LAUNCH_LOCK = threading.RLock()


def _meipass() -> str:
    value = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if not value:
        return ""
    try:
        return os.path.normcase(os.path.realpath(value))
    except Exception:
        return os.path.normcase(value)


def _inside_mei(path: str, root: str) -> bool:
    if not path or not root:
        return False
    try:
        candidate = os.path.normcase(os.path.realpath(path.strip('"')))
        common = os.path.commonpath([candidate, root])
        return common == root
    except Exception:
        return False


def sanitized_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Убирает `_MEI` из PATH, не меняя окружение основного процесса."""
    env = dict(base if base is not None else os.environ)
    root = _meipass()
    if not root:
        return env

    path_value = str(env.get("PATH") or "")
    if path_value:
        entries = [item for item in path_value.split(os.pathsep) if item]
        entries = [item for item in entries if not _inside_mei(item, root)]
        env["PATH"] = os.pathsep.join(entries)
    return env


def _get_windows_dll_directory() -> str | None:
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.windll.kernel32
        k32.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
        k32.GetDllDirectoryW.restype = ctypes.c_uint32
        needed = int(k32.GetDllDirectoryW(0, None))
        if needed <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(needed + 1)
        k32.GetDllDirectoryW(len(buffer), buffer)
        return str(buffer.value or "")
    except Exception:
        return None


def _set_windows_dll_directory(path: str | None) -> None:
    if os.name != "nt":
        return
    try:
        k32 = ctypes.windll.kernel32
        k32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        k32.SetDllDirectoryW.restype = ctypes.c_bool
        k32.SetDllDirectoryW(path if path else None)
    except Exception:
        pass


def popen_external(args: Iterable[str] | list[str], **kwargs: Any) -> subprocess.Popen[Any]:
    """Создаёт внешний процесс без наследования DLL search path PyInstaller."""
    if "env" in kwargs:
        kwargs["env"] = sanitized_environment(kwargs.get("env"))
    else:
        kwargs["env"] = sanitized_environment()

    if os.name != "nt":
        return subprocess.Popen(list(args), **kwargs)

    with _LAUNCH_LOCK:
        previous = _get_windows_dll_directory()
        _set_windows_dll_directory(None)
        try:
            return subprocess.Popen(list(args), **kwargs)
        finally:
            # None означает, что прочитать исходное значение не удалось. В frozen
            # приложении PyInstaller ожидает _MEIPASS; вне frozen оставляем default.
            if previous is None:
                previous = str(getattr(sys, "_MEIPASS", "") or "") or None
            _set_windows_dll_directory(previous or None)


def run_external(args: Iterable[str] | list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Эквивалент subprocess.run(), но DLL isolation действует только на Popen."""
    input_data = kwargs.pop("input", None)
    timeout = kwargs.pop("timeout", None)
    check = bool(kwargs.pop("check", False))
    capture_output = bool(kwargs.pop("capture_output", False))

    if input_data is not None and kwargs.get("stdin") is not None:
        raise ValueError("stdin and input arguments may not both be used")
    if input_data is not None:
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout/stderr and capture_output may not be used together")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    process = popen_external(args, **kwargs)
    try:
        stdout, stderr = process.communicate(input_data, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        exc.stdout = stdout
        exc.stderr = stderr
        raise

    result = subprocess.CompletedProcess(list(args), process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
