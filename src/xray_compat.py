# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable


_INSTALLED = False


def install_xray_config_compat() -> None:
    """Нормализует VLESS streamSettings под актуальный формат Xray-core.

    В старом генераторе транспорт записывался в поле ``method``. Xray-core
    ожидает ``network``; неизвестное поле игнорируется, поэтому Xray запускал
    локальный SOCKS, но пытался подключаться транспортом RAW. В результате WS,
    gRPC и XHTTP выглядели как рабочий Xray-процесс, однако HTTPS-проверка
    всегда завершалась ошибкой.
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

        # Xray-core использует streamSettings.network. Поле method относится к
        # HTTP-заголовкам и не выбирает транспорт соединения.
        method = stream.pop("method", None)
        if method and not stream.get("network"):
            stream["network"] = method

        # password пока принимается Xray как legacy-alias publicKey, но в новых
        # конфигурациях используем официальное имя поля.
        reality = stream.get("realitySettings")
        if isinstance(reality, dict):
            password = reality.pop("password", None)
            if password and not reality.get("publicKey"):
                reality["publicKey"] = password

        return outbound

    setattr(fixed_builder, "_prostokvn_xray_compat", True)
    node_tester.make_xray_vless_outbound = fixed_builder
    _INSTALLED = True
