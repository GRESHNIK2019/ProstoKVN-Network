# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import sys

import apply_gui_v022 as migration


if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def replace_first(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count < 1:
        raise RuntimeError(f"{label}: совпадение не найдено")
    return source.replace(old, new, 1)


_real_parse = migration.ast.parse


def parse_with_repair(source: str, *args, **kwargs):
    # В старом одноразовом шаблоне \n внутри вставляемого метода превращался
    # в реальный перевод строки. Исправляем только этот известный фрагмент.
    broken = "reason.replace('\n', ' | ')"
    fixed = r"reason.replace('\n', ' | ')"
    if broken in source:
        source = source.replace(broken, fixed)
        migration.GUI_PATH.write_text(source, encoding="utf-8", newline="\n")
    return _real_parse(source, *args, **kwargs)


migration.replace_once = replace_first
migration.ast.parse = parse_with_repair
migration.main()
