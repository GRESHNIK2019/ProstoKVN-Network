# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import base64
import ctypes
import os


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _make_blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(data), pointer), buffer


def _protect_windows(data: bytes) -> bytes:
    input_blob, input_buffer = _make_blob(data)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "ProstoKVN Network",
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not ok:
        raise OSError("Windows DPAPI не смог зашифровать данные")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _unprotect_windows(data: bytes) -> bytes:
    input_blob, input_buffer = _make_blob(data)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not ok:
        raise OSError("Windows DPAPI не смог расшифровать данные")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def protect_text(value: str) -> str:
    """Шифрует строку для хранения в локальных настройках пользователя."""
    value = str(value or "")
    if not value:
        return ""

    raw = value.encode("utf-8")
    if os.name == "nt":
        protected = _protect_windows(raw)
        return "dpapi:" + base64.b64encode(protected).decode("ascii")

    # Нужен для разработки и unit-тестов вне Windows. В Windows этот путь не используется.
    return "plain:" + base64.b64encode(raw).decode("ascii")


def unprotect_text(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""

    if value.startswith("dpapi:"):
        if os.name != "nt":
            raise OSError("DPAPI-данные можно расшифровать только в Windows-профиле владельца")
        raw = base64.b64decode(value[6:].encode("ascii"))
        return _unprotect_windows(raw).decode("utf-8")

    if value.startswith("plain:"):
        raw = base64.b64decode(value[6:].encode("ascii"))
        return raw.decode("utf-8")

    # Совместимость со старыми settings.json, где URL хранился открытым текстом.
    return value
