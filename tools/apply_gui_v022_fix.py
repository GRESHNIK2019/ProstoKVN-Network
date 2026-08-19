# -*- coding: utf-8 -*-
from __future__ import annotations

import apply_gui_v022 as migration


def replace_first(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count < 1:
        raise RuntimeError(f"{label}: совпадение не найдено")
    return source.replace(old, new, 1)


migration.replace_once = replace_first
migration.main()
