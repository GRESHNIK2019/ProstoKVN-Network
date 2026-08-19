# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable


_INSTALLED = False


def install_xray_config_compat() -> None:
    """Нормализует VLESS streamSettings для совместимости версий Xray-core.

    Часть установленных у пользователей Xray-core ожидает традиционные поля
    ``network`` и ``publicKey``. Более новые версии принимают также алиасы
    ``method`` и ``password``, но использование только новых алиасов ломает
    совместимость со старыми уже установленными ядрами.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    import node_tester

    original: Callable[[Any], dict[str, Any]] = node_tester.make_xray_vless_outbound
    if getattr(original, "_prostokvn_xray_compat", False):
        _INSTALLED = True
        return

    def fixed_builder(node: Any) -> dict[str, Any]:
        outbound = original(node)
        stream = outbound.get("streamSettings")
        if not isinstance(stream, dict):
            return outbound

        method = stream.pop("method", None)
        if method and not stream.get("network"):
            stream["network"] = method

        reality = stream.get("realitySettings")
        if isinstance(reality, dict):
            password = reality.pop("password", None)
            if password and not reality.get("publicKey"):
                reality["publicKey"] = password

        return outbound

    setattr(fixed_builder, "_prostokvn_xray_compat", True)
    node_tester.make_xray_vless_outbound = fixed_builder
    _INSTALLED = True
