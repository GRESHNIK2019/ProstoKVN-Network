# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any

from xray_compat import install_xray_config_compat


# node_tester загружается раньше routing/settings_store в основном приложении и
# в vpn_runner. Здесь ставим небольшой compatibility-layer до первого запуска
# проверки узлов или Xray-моста.
install_xray_config_compat()


# Эти ключи управляются отдельными страницами настроек. Основной экран старых
# версий о них не знает, поэтому при обычном сохранении их нельзя терять.
_PRESERVE_IF_MISSING = ("route_rules",)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_settings(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    if data is not None:
        return data

    backup = path.with_name(path.name + ".bak")
    data = _read_json(backup)
    return data if data is not None else {}


def save_settings(path: Path, data: dict[str, Any]) -> None:
    current = _read_json(path) or {}
    payload = dict(data)
    for key in _PRESERVE_IF_MISSING:
        if key not in payload and key in current:
            payload[key] = current[key]

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    backup = path.with_name(path.name + ".bak")

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with temp.open("w", encoding="utf-8", newline="\n") as file:
        file.write(text)
        file.flush()
        os.fsync(file.fileno())

    os.replace(temp, path)

    # Backup создаём уже из нового файла. Так после миграции со старой версии
    # в .bak не остаётся открытый URL подписки.
    try:
        shutil.copy2(path, backup)
    except Exception:
        pass
