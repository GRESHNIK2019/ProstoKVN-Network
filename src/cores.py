# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Установка и поиск проверенных VPN-ядер.

Ключевой принцип: установленное/запущенное ядро никогда не заменяется на месте.
Каждая проверенная версия живёт в своём каталоге (``xray-26.7.28`` и
``sing-box-1.13.14``), поэтому Windows file locking не мешает обновлению.
"""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable
import urllib.parse
import urllib.request
import uuid
import zipfile

from app_config import TESTED_SINGBOX_VERSION, TESTED_XRAY_VERSION
from paths import APP_DIR, MANAGED_CORE_DIR

CORE_ARCHIVE_MAX_BYTES = 256 * 1024 * 1024
RELEASE_JSON_MAX_BYTES = 4 * 1024 * 1024


def _windows_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return "amd64"


def _release_api_url(repo: str, version: str) -> str:
    tag = "v" + str(version or "").strip().lstrip("v")
    if tag == "v":
        raise ValueError("Не задана версия VPN-ядра")
    return f"https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"


def _github_release(repo: str, version: str) -> dict[str, Any]:
    req = urllib.request.Request(
        _release_api_url(repo, version),
        headers={
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/2.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read(RELEASE_JSON_MAX_BYTES + 1)
    if len(raw) > RELEASE_JSON_MAX_BYTES:
        raise RuntimeError("GitHub вернул слишком большой ответ для описания релиза.")
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise RuntimeError("GitHub вернул некорректное описание релиза.")

    expected_tag = "v" + str(version).strip().lstrip("v")
    actual_tag = str(data.get("tag_name") or "")
    if actual_tag != expected_tag:
        raise RuntimeError(f"Ожидался релиз {expected_tag}, GitHub вернул {actual_tag or 'без тега'}.")
    return data


def _find_release_asset(release: dict[str, Any], matcher: Callable[[str], bool]) -> dict[str, Any]:
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if matcher(name):
            return asset
    raise RuntimeError("В закреплённом GitHub-релизе не найден подходящий Windows-архив.")


def _download_file(url: str, dest: Path, progress: Callable[[str], None] | None = None) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/2.0",
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        if total > CORE_ARCHIVE_MAX_BYTES:
            raise RuntimeError("Архив VPN-ядра превышает допустимый размер.")
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            done += len(chunk)
            if done > CORE_ARCHIVE_MAX_BYTES:
                raise RuntimeError("Архив VPN-ядра превышает допустимый размер.")
            fh.write(chunk)
            if progress and total > 0:
                progress(f"Загрузка: {min(100, int(done * 100 / total))}%")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _verify_github_asset_digest(path: Path, asset: dict[str, Any]) -> None:
    """Если GitHub публикует SHA-256 asset digest, сверяем его обязательно."""
    digest = str(asset.get("digest") or "").strip().lower()
    if not digest.startswith("sha256:"):
        return
    expected = digest.split(":", 1)[1]
    if _sha256(path) != expected:
        raise RuntimeError("SHA256 загруженного компонента не совпадает с GitHub release asset.")


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        total_unpacked = 0
        for member in zf.infolist():
            total_unpacked += max(0, int(member.file_size or 0))
            if total_unpacked > CORE_ARCHIVE_MAX_BYTES * 2:
                raise RuntimeError("Распакованный VPN-core превышает допустимый размер.")
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"Небезопасный путь в архиве VPN-ядра: {member.filename}") from exc
        zf.extractall(destination)


def _core_target(kind: str, version: str) -> Path:
    normalized = str(version).strip().lstrip("v")
    return MANAGED_CORE_DIR / f"{kind}-{normalized}"


def _install_directory_side_by_side(source_dir: Path, target: Path) -> None:
    """Устанавливает новый каталог, не переименовывая старый работающий core."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return

    staging = target.with_name(target.name + f".new-{uuid.uuid4().hex[:8]}")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(source_dir, staging)
        try:
            staging.replace(target)
        except FileExistsError:
            # Другая копия приложения успела установить ту же версию.
            pass
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _extract_version_text(text: str, kind: str) -> str | None:
    text = str(text or "")
    patterns = (
        r"(?i)sing-box\s+version\s+v?([0-9]+(?:\.[0-9]+){1,3})",
        r"(?i)\bxray\s+v?([0-9]+(?:\.[0-9]+){1,3})",
    )
    preferred = patterns[0] if kind == "sing-box" else patterns[1]
    match = re.search(preferred, text)
    if not match:
        match = re.search(r"(?<![0-9])v?([0-9]+(?:\.[0-9]+){2,3})(?![0-9])", text)
    return match.group(1) if match else None


def detect_core_version(path: Path, kind: str, timeout: float = 3.0) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        result = subprocess.run(
            [str(path), "version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        return _extract_version_text(text, kind)
    except Exception:
        return None


def _expected_version(kind: str) -> str:
    return TESTED_SINGBOX_VERSION if kind == "sing-box" else TESTED_XRAY_VERSION


def _is_compatible(path: Path, kind: str, *, allow_unknown: bool = False) -> bool:
    version = detect_core_version(path, kind)
    if version is None:
        return bool(allow_unknown)
    return version == _expected_version(kind)


def _managed_exact(kind: str) -> Path:
    target = _core_target(kind, _expected_version(kind))
    name = "sing-box.exe" if kind == "sing-box" else "xray.exe"
    return target / name


def _legacy_managed(kind: str) -> Path:
    name = "sing-box.exe" if kind == "sing-box" else "xray.exe"
    return MANAGED_CORE_DIR / kind / name


def _candidate(path: Path, kind: str, *, allow_unknown: bool = False) -> Path | None:
    if not path.is_file():
        return None
    return path.resolve() if _is_compatible(path, kind, allow_unknown=allow_unknown) else None


def install_official_cores(
    progress: Callable[[str], None] | None = None,
    install_singbox: bool = True,
    install_xray: bool = True,
) -> dict[str, Path]:
    """Скачивает только закреплённые официальные Windows-релизы.

    Каталоги версионированы, поэтому обновление не пытается удалить или
    переименовать работающий ``xray.exe``/``sing-box.exe``.
    """
    def emit(text: str) -> None:
        if progress:
            progress(text)

    arch = _windows_arch()
    result: dict[str, Path] = {}
    MANAGED_CORE_DIR.mkdir(parents=True, exist_ok=True)

    if install_singbox:
        target = _core_target("sing-box", TESTED_SINGBOX_VERSION)
        existing = target / "sing-box.exe"
        if existing.is_file() and _is_compatible(existing, "sing-box", allow_unknown=False):
            result["singbox"] = existing.resolve()
            emit(f"sing-box: v{TESTED_SINGBOX_VERSION} уже установлена")
        else:
            emit(f"sing-box: загружаю проверенную версию {TESTED_SINGBOX_VERSION}...")
            release = _github_release("SagerNet/sing-box", TESTED_SINGBOX_VERSION)
            expected_name = f"sing-box-{TESTED_SINGBOX_VERSION}-windows-{'arm64' if arch == 'arm64' else 'amd64'}.zip"
            asset = _find_release_asset(release, lambda name: name.lower() == expected_name.lower())
            url = str(asset.get("browser_download_url") or "")
            if not url:
                raise RuntimeError("GitHub не вернул ссылку на sing-box release asset.")
            with tempfile.TemporaryDirectory(prefix="prostokvn-singbox-") as td:
                root = Path(td)
                archive = root / str(asset["name"])
                _download_file(url, archive, lambda text: emit(f"sing-box: {text}"))
                _verify_github_asset_digest(archive, asset)
                extracted = root / "extract"
                extracted.mkdir()
                _safe_extract_zip(archive, extracted)
                exe = next(extracted.rglob("sing-box.exe"), None)
                if exe is None:
                    raise RuntimeError("В официальном архиве sing-box не найден sing-box.exe.")
                _install_directory_side_by_side(exe.parent, target)
            installed = target / "sing-box.exe"
            if not installed.is_file():
                raise RuntimeError("sing-box распакован, но итоговый EXE не найден.")
            detected = detect_core_version(installed, "sing-box")
            if detected and detected != TESTED_SINGBOX_VERSION:
                raise RuntimeError(f"Установлен неожиданный sing-box {detected} вместо {TESTED_SINGBOX_VERSION}.")
            result["singbox"] = installed.resolve()
            emit(f"sing-box: установлен v{TESTED_SINGBOX_VERSION}")

    if install_xray:
        target = _core_target("xray", TESTED_XRAY_VERSION)
        existing = target / "xray.exe"
        if existing.is_file() and _is_compatible(existing, "xray", allow_unknown=False):
            result["xray"] = existing.resolve()
            emit(f"Xray: v{TESTED_XRAY_VERSION} уже установлен")
        else:
            emit(f"Xray: загружаю проверенную версию {TESTED_XRAY_VERSION}...")
            release = _github_release("XTLS/Xray-core", TESTED_XRAY_VERSION)
            expected_name = "xray-windows-arm64-v8a.zip" if arch == "arm64" else "xray-windows-64.zip"
            asset = _find_release_asset(release, lambda name: name.lower() == expected_name)
            url = str(asset.get("browser_download_url") or "")
            if not url:
                raise RuntimeError("GitHub не вернул ссылку на Xray release asset.")
            with tempfile.TemporaryDirectory(prefix="prostokvn-xray-") as td:
                root = Path(td)
                archive = root / str(asset["name"])
                _download_file(url, archive, lambda text: emit(f"Xray: {text}"))
                _verify_github_asset_digest(archive, asset)
                extracted = root / "extract"
                extracted.mkdir()
                _safe_extract_zip(archive, extracted)
                exe = next(extracted.rglob("xray.exe"), None)
                if exe is None:
                    raise RuntimeError("В официальном архиве Xray не найден xray.exe.")
                _install_directory_side_by_side(exe.parent, target)
            installed = target / "xray.exe"
            if not installed.is_file():
                raise RuntimeError("Xray распакован, но итоговый EXE не найден.")
            detected = detect_core_version(installed, "xray")
            if detected and detected != TESTED_XRAY_VERSION:
                raise RuntimeError(f"Установлен неожиданный Xray {detected} вместо {TESTED_XRAY_VERSION}.")
            result["xray"] = installed.resolve()
            emit(f"Xray: установлен v{TESTED_XRAY_VERSION}")

    return result


def find_singbox_binary(explicit: str = "") -> Path:
    kind = "sing-box"
    if explicit:
        candidate = _candidate(Path(explicit).expanduser(), kind, allow_unknown=False)
        if candidate:
            return candidate
    env = os.environ.get("SINGBOX_EXE")
    if env:
        candidate = _candidate(Path(env), kind, allow_unknown=False)
        if candidate:
            return candidate

    exact = _managed_exact(kind)
    if exact.is_file():
        return exact.resolve()

    # Совместимость со старой раскладкой и unit-test fixtures. Реальный EXE с
    # распознаваемой чужой версией здесь отвергается; unknown допускается только
    # для legacy managed-каталога.
    legacy = _legacy_managed(kind)
    candidate = _candidate(legacy, kind, allow_unknown=True)
    if candidate:
        return candidate

    roots = [
        Path(r"C:\Program Files (x86)\v2rayN-windows-64"),
        Path(r"C:\Program Files\v2rayN-windows-64"),
        Path.home() / "Desktop" / "v2rayN-windows-64",
        APP_DIR,
    ]
    names = ["sing-box.exe", "sing-box-client.exe"]
    for root in roots:
        if not root.exists():
            continue
        for name in names:
            for path in (root / "bin" / "sing_box" / name, root / name):
                candidate = _candidate(path, kind, allow_unknown=False)
                if candidate:
                    return candidate
    for root in roots[:2]:
        if not root.exists():
            continue
        try:
            for name in names:
                for path in root.glob(f"**/{name}"):
                    candidate = _candidate(path, kind, allow_unknown=False)
                    if candidate:
                        return candidate
        except Exception:
            pass
    raise FileNotFoundError(
        f"Не найден совместимый sing-box v{TESTED_SINGBOX_VERSION}. "
        "ProstoKVN Network может установить проверенный core автоматически."
    )


def find_xray_binary(explicit: str = "") -> Path:
    kind = "xray"
    if explicit:
        candidate = _candidate(Path(explicit).expanduser(), kind, allow_unknown=False)
        if candidate:
            return candidate
    env = os.environ.get("XRAY_EXE")
    if env:
        candidate = _candidate(Path(env), kind, allow_unknown=False)
        if candidate:
            return candidate

    exact = _managed_exact(kind)
    if exact.is_file():
        return exact.resolve()

    legacy = _legacy_managed(kind)
    candidate = _candidate(legacy, kind, allow_unknown=True)
    if candidate:
        return candidate

    roots = [
        Path(r"C:\Program Files (x86)\v2rayN-windows-64"),
        Path(r"C:\Program Files\v2rayN-windows-64"),
        Path.home() / "Desktop" / "v2rayN-windows-64",
        APP_DIR,
    ]
    for root in roots:
        if not root.exists():
            continue
        for rel in (Path("bin") / "xray" / "xray.exe", Path("bin") / "Xray" / "xray.exe", Path("xray.exe")):
            candidate = _candidate(root / rel, kind, allow_unknown=False)
            if candidate:
                return candidate
    for root in roots[:2]:
        if not root.exists():
            continue
        try:
            for path in root.glob("**/xray.exe"):
                candidate = _candidate(path, kind, allow_unknown=False)
                if candidate:
                    return candidate
        except Exception:
            pass
    raise FileNotFoundError(
        f"Не найден совместимый Xray v{TESTED_XRAY_VERSION}. "
        "ProstoKVN Network может установить проверенный core автоматически."
    )
