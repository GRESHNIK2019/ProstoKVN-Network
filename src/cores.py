# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
from typing import Any, Callable
import urllib.parse
import urllib.request
import zipfile

from app_config import TESTED_SINGBOX_VERSION, TESTED_XRAY_VERSION
from paths import APP_DIR, MANAGED_CORE_DIR

CORE_ARCHIVE_MAX_BYTES = 256 * 1024 * 1024


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
    url = _release_api_url(repo, version)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
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
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/1.0",
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
                pct = min(100, int(done * 100 / total))
                progress(f"Загрузка: {pct}%")


def _verify_github_asset_digest(path: Path, asset: dict[str, Any]) -> None:
    """Если GitHub публикует SHA-256 asset digest, сверяем его обязательно."""
    digest = str(asset.get("digest") or "").strip().lower()
    if not digest.startswith("sha256:"):
        return
    expected = digest.split(":", 1)[1]
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest().lower() != expected:
        raise RuntimeError("SHA256 загруженного компонента не совпадает с GitHub release asset.")


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    """Распаковывает ZIP без возможности записать файлы за пределы staging."""
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"Небезопасный путь в архиве VPN-ядра: {member.filename}") from exc
        zf.extractall(destination)


def _replace_directory(staging: Path, target: Path) -> None:
    old = target.with_name(target.name + ".old")
    try:
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            target.replace(old)
        staging.replace(target)
        shutil.rmtree(old, ignore_errors=True)
    except Exception:
        if not target.exists() and old.exists():
            old.replace(target)
        raise


def install_official_cores(
    progress: Callable[[str], None] | None = None,
    install_singbox: bool = True,
    install_xray: bool = True,
) -> dict[str, Path]:
    """Скачивает закреплённые и проверенные версии официальных Windows-ядер."""
    def emit(text: str) -> None:
        if progress:
            progress(text)

    arch = _windows_arch()
    result: dict[str, Path] = {}
    MANAGED_CORE_DIR.mkdir(parents=True, exist_ok=True)

    if install_singbox:
        emit(f"sing-box: проверяю закреплённую версию {TESTED_SINGBOX_VERSION}...")
        release = _github_release("SagerNet/sing-box", TESTED_SINGBOX_VERSION)
        if arch == "arm64":
            expected_name = f"sing-box-{TESTED_SINGBOX_VERSION}-windows-arm64.zip"
        else:
            expected_name = f"sing-box-{TESTED_SINGBOX_VERSION}-windows-amd64.zip"
        asset = _find_release_asset(release, lambda name: name.lower() == expected_name.lower())
        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("GitHub не вернул ссылку на sing-box release asset.")

        with tempfile.TemporaryDirectory(prefix="prostokvn-singbox-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            _download_file(url, archive, lambda text: emit(f"sing-box: {text}"))
            _verify_github_asset_digest(archive, asset)

            extracted = td_path / "extract"
            extracted.mkdir()
            _safe_extract_zip(archive, extracted)

            exe = next(extracted.rglob("sing-box.exe"), None)
            if exe is None:
                raise RuntimeError("В официальном архиве sing-box не найден sing-box.exe.")

            source_dir = exe.parent
            staging = MANAGED_CORE_DIR / "sing-box.new"
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(source_dir, staging)
            target = MANAGED_CORE_DIR / "sing-box"
            _replace_directory(staging, target)

        result["singbox"] = (MANAGED_CORE_DIR / "sing-box" / "sing-box.exe").resolve()
        emit(f"sing-box: установлен v{TESTED_SINGBOX_VERSION}")

    if install_xray:
        emit(f"Xray: проверяю закреплённую версию {TESTED_XRAY_VERSION}...")
        release = _github_release("XTLS/Xray-core", TESTED_XRAY_VERSION)
        expected = "xray-windows-arm64-v8a.zip" if arch == "arm64" else "xray-windows-64.zip"
        asset = _find_release_asset(release, lambda name: name.lower() == expected)
        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("GitHub не вернул ссылку на Xray release asset.")

        with tempfile.TemporaryDirectory(prefix="prostokvn-xray-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            _download_file(url, archive, lambda text: emit(f"Xray: {text}"))
            _verify_github_asset_digest(archive, asset)

            extracted = td_path / "extract"
            extracted.mkdir()
            _safe_extract_zip(archive, extracted)

            exe = next(extracted.rglob("xray.exe"), None)
            if exe is None:
                raise RuntimeError("В официальном архиве Xray не найден xray.exe.")

            source_dir = exe.parent
            staging = MANAGED_CORE_DIR / "xray.new"
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(source_dir, staging)
            target = MANAGED_CORE_DIR / "xray"
            _replace_directory(staging, target)

        result["xray"] = (MANAGED_CORE_DIR / "xray" / "xray.exe").resolve()
        emit(f"Xray: установлен v{TESTED_XRAY_VERSION}")

    return result


def find_singbox_binary(explicit: str = "") -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path.resolve()
    env = os.environ.get("SINGBOX_EXE")
    if env and Path(env).is_file():
        return Path(env).resolve()

    managed = MANAGED_CORE_DIR / "sing-box" / "sing-box.exe"
    if managed.is_file():
        return managed.resolve()

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
            path = root / "bin" / "sing_box" / name
            if path.is_file():
                return path.resolve()
            path = root / name
            if path.is_file():
                return path.resolve()
    for root in roots[:2]:
        if not root.exists():
            continue
        try:
            for name in names:
                for path in root.glob(f"**/{name}"):
                    if path.is_file():
                        return path.resolve()
        except Exception:
            pass
    raise FileNotFoundError("Не найден sing-box.exe. ProstoKVN Network может установить официальный core автоматически.")


def find_xray_binary(explicit: str = "") -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path.resolve()
    env = os.environ.get("XRAY_EXE")
    if env and Path(env).is_file():
        return Path(env).resolve()
    managed = MANAGED_CORE_DIR / "xray" / "xray.exe"
    if managed.is_file():
        return managed.resolve()
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
            path = root / rel
            if path.is_file():
                return path.resolve()
    for root in roots[:2]:
        if not root.exists():
            continue
        try:
            for path in root.glob("**/xray.exe"):
                if path.is_file():
                    return path.resolve()
        except Exception:
            pass
    raise FileNotFoundError("Не найден xray.exe. ProstoKVN Network может установить официальный core автоматически.")
