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

from app_config import UPDATE_SIGNER_SUBJECTS
from external_process import popen_external, run_external


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
        raise RuntimeError("GitHub Release не содержит tag_name.")
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
        raise RuntimeError(f"В Release v{latest} нет файла {exe_asset}.")
    if not hash_url:
        raise RuntimeError(f"В Release v{latest} нет файла {hash_asset}.")

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

    request = urllib.request.Request(
        str(info["exe_url"]),
        headers={"User-Agent": f"ProstoKVNNetwork/{current_version}"},
    )
    with urllib.request.urlopen(request, timeout=90) as response, exe_path.open("wb") as output:
        shutil.copyfileobj(response, output)

    expected_hash = _download_expected_hash(str(info.get("hash_url") or ""), current_version)
    actual_hash = _sha256(exe_path)
    if not expected_hash or actual_hash != expected_hash:
        exe_path.unlink(missing_ok=True)
        raise RuntimeError("SHA-256 обновления не совпадает.")

    try:
        verify_authenticode(exe_path)
    except Exception:
        exe_path.unlink(missing_ok=True)
        raise

    return exe_path


def _download_expected_hash(hash_url: str, current_version: str) -> str:
    if not hash_url:
        return ""
    request = urllib.request.Request(
        hash_url,
        headers={"User-Agent": f"ProstoKVNNetwork/{current_version}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        text = response.read().decode("ascii", errors="ignore").strip()
    return (text.split() or [""])[0].strip().lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def signer_subject_is_allowed(subject: str, allowed_subjects: tuple[str, ...] | list[str]) -> bool:
    normalized = str(subject or "").casefold()
    if not normalized:
        return False
    expected = [str(value or "").strip().casefold() for value in allowed_subjects]
    expected = [value for value in expected if value]
    return bool(expected) and any(value in normalized for value in expected)


def verify_authenticode(path: Path, allowed_subjects: tuple[str, ...] | list[str] | None = None) -> str:
    if os.name != "nt":
        return "not-windows"

    allowed = tuple(allowed_subjects or UPDATE_SIGNER_SUBJECTS)
    if not allowed:
        raise RuntimeError("Не задан доверенный издатель обновлений.")

    escaped = str(path.resolve()).replace("'", "''")
    script = (
        f"$s = Get-AuthenticodeSignature -LiteralPath '{escaped}'; "
        "$o = [PSCustomObject]@{Status=[string]$s.Status; Subject=''}; "
        "if ($s.SignerCertificate) {$o.Subject=[string]$s.SignerCertificate.Subject}; "
        "$o | ConvertTo-Json -Compress"
    )
    result = run_external(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError("Не удалось проверить цифровую подпись обновления.")

    try:
        data = json.loads((result.stdout or "").strip())
    except Exception as exc:
        raise RuntimeError("Windows вернул некорректный результат проверки подписи.") from exc

    status = str(data.get("Status") or "")
    subject = str(data.get("Subject") or "")
    if status != "Valid":
        raise RuntimeError(f"Цифровая подпись обновления недействительна: {status or 'Unknown'}.")
    if not signer_subject_is_allowed(subject, allowed):
        raise RuntimeError(
            "Обновление подписано неизвестным издателем: "
            + (subject or "сертификат не содержит Subject")
        )
    return subject


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
    # updater намеренно переживает основной процесс, поэтому особенно важно не
    # позволить cmd.exe наследовать PyInstaller SetDllDirectory(_MEI...).
    popen_external(
        ["cmd.exe", "/c", str(updater)],
        cwd=str(new_exe.parent),
        creationflags=flags,
    )
