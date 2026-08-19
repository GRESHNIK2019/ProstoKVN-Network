# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    backup = path.with_name(path.name + ".bak")

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
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
