# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Совместимый фасад для старых импортов.

Новый Xray builder сразу генерирует ``network`` и ``publicKey`` в
``protocol_engine.py``. Runtime monkey-patch больше не нужен, но функция
оставлена, чтобы старые импорты и тесты не ломались.
"""

_INSTALLED = False


def install_xray_config_compat() -> None:
    global _INSTALLED
    _INSTALLED = True
