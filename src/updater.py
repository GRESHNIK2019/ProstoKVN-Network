# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request


def version_tuple(value: str) -> tuple[int, ...]:
    value = str(value or "").strip().lower().lstrip("v")
    parts: list[int] = []
    for item in value.split("."):
        match = re.match(r"(\d+)", item)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def check_latest_release(current_version: str, api_url: str, exe_asset: str, hash_asset: str) -> dict | None:
    request = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": f"ProstoKVNNetwork/{current_version}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))

    latest = str(data.get("tag_name") or "").strip().lstrip("v")
    if not latest:
        raise RuntimeError("GitHub Release Ð½Ðµ ÑÐ¾Ð´ÐµÑ€Ð¶Ð¸Ñ‚ tag_name.")
    if version_tuple(latest) <= version_tuple(current_version):
        return None

    exe_url = ""
    hash_url = ""
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        if name == exe_asset:
            exe_url = str(asset.get("browser_download_url") or "")
        elif name == hash_asset:
            hash_url = str(asset.get("browser_download_url") or "")

    if not exe_url:
        raise RuntimeError(f"Ð’ Release v{latest} Ð½ÐµÑ‚ Ñ„Ð°Ð¹Ð»Ð° {exe_asset}.")

    return {
        "version": latest,
        "exe_url": exe_url,
        "hash_url": hash_url,
        "notes": str(data.get("body") or "").strip(),
    }


def download_update(info: dict, current_version: str) -> Path:
    update_dir = Path(tempfile.gettempdir()) / "ProstoKVNNetwork_Update"
    update_dir.mkdir(parents=True, exist_ok=True)
    exe_path = update_dir / "ProstoKVNNetwork.new.exe"

    request = urllib.request.Request(str(info["exe_url"]), headers={"User-Agent": f"ProstoKVNNetwork/{current_version}"})
    with urllib.request.urlopen(request, timeout=90) as response, exe_path.open("wb") as output:
        shutil.copyfileobj(response, output)

    expected_hash = _download_expected_hash(str(info.get("hash_url") or ""), current_version)
    if expected_hash and _sha256(exe_path) != expected_hash:
        exe_path.unlink(missing_ok=True)
        raise RuntimeError("SHA-256 Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð½Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´Ð°ÐµÑ‚.")
    return exe_path


def _download_expected_hash(hash_url: str, current_version: str) -> str:
    if not hash_url:
        return ""
    request = urllib.request.Request(hash_url, headers={"User-Agent": f"ProstoKVNNetwork/{current_version}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        text = response.read().decode("ascii", errors="ignore").strip()
    return (text.split() or [""])[0].strip().lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def launch_self_updater(new_exe: Path, current_exe: Path, pid: int) -> None:
    new_exe = new_exe.resolve()
    current_exe = current_exe.resolve()
    updater = new_exe.parent / "ProstoKVNNetwork_updater.cmd"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f'set "PID={pid}"',
        f'set "NEW={new_exe}"',
        f'set "DST={current_exe}"',
        ":wait",
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul',
        "if not errorlevel 1 (",
        "    timeout /t 1 /nobreak >nul",
        "    goto wait",
        ")",
        'copy /Y "%NEW%" "%DST%" >nul',
        "if errorlevel 1 exit /b 1",
        'start "" "%DST%"',
        'del /Q "%NEW%" >nul 2>&1',
        'del /Q "%~f0" >nul 2>&1',
    ]
    updater.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    subprocess.Popen(["cmd.exe", "/c", str(updater)], cwd=str(new_exe.parent), creationflags=flags)
