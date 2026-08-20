# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path
import shutil

APP_DIR = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA") or APP_DIR)
LEGACY_USER_DATA_DIRS = (
    DATA_ROOT / ("Smart" + "VPN"),
    DATA_ROOT / ("Motor" + "festVPN_AutoSelector"),
)
USER_DATA_DIR = DATA_ROOT / "ProstoKVN Network"

# Одноразово переносим настройки из старых каталогов, если новый ещё не создан.
if not USER_DATA_DIR.exists():
    for old_dir in LEGACY_USER_DATA_DIRS:
        if not old_dir.exists():
            continue
        try:
            shutil.copytree(old_dir, USER_DATA_DIR, dirs_exist_ok=True)
            break
        except Exception:
            pass

USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# В PyInstaller --onefile __file__ расположен внутри временного _MEI-каталога.
# Нельзя хранить там runtime-конфиги и логи внешних xray/sing-box: дочерний
# процесс может удерживать временную папку открытой и мешать bootloader удалить её.
RUNTIME_DIR = USER_DATA_DIR / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = USER_DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

BLOCKLIST_DIR = USER_DATA_DIR / "blocklists"
BLOCKLIST_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = USER_DATA_DIR / "settings.json"
MANAGED_CORE_DIR = USER_DATA_DIR / "cores"
MANAGED_CORE_DIR.mkdir(parents=True, exist_ok=True)
BLOCKLIST_META_PATH = BLOCKLIST_DIR / "meta.json"
