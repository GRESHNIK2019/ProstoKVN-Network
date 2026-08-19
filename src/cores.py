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
import urllib.request
import zipfile

from paths import APP_DIR, MANAGED_CORE_DIR

def _windows_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return "amd64"


def _github_latest_release(repo: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ProstoKVNNetwork-CoreBootstrap/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _find_release_asset(release: dict[str, Any], matcher: Callable[[str], bool]) -> dict[str, Any]:
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if matcher(name):
            return asset
    raise RuntimeError("В последнем GitHub-релизе не найден подходящий Windows-архив.")


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
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress and total > 0:
                pct = int(done * 100 / total)
                progress(f"Загрузка: {pct}%")


def _verify_github_asset_digest(path: Path, asset: dict[str, Any]) -> None:
    """
    GitHub Asset API на новых релизах может возвращать digest=sha256:...
    Если поле есть — обязательно сверяем. Если его нет — файл всё равно скачан
    непосредственно с официального github.com release asset URL.
    """
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
    """
    Скачивает официальные Windows-релизы непосредственно с GitHub:
      SagerNet/sing-box
      XTLS/Xray-core

    Устанавливает в %LOCALAPPDATA%/ProstoKVN Network/cores.
    """
    def emit(text: str) -> None:
        if progress:
            progress(text)

    arch = _windows_arch()
    result: dict[str, Path] = {}
    MANAGED_CORE_DIR.mkdir(parents=True, exist_ok=True)

    if install_singbox:
        emit("sing-box: получаю информацию о последнем официальном релизе...")
        release = _github_latest_release("SagerNet/sing-box")
        if arch == "arm64":
            matcher = lambda n: n.lower().endswith("-windows-arm64.zip") and n.lower().startswith("sing-box-")
        else:
            matcher = lambda n: n.lower().endswith("-windows-amd64.zip") and n.lower().startswith("sing-box-")
        asset = _find_release_asset(release, matcher)
        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("GitHub не вернул ссылку на sing-box release asset.")

        with tempfile.TemporaryDirectory(prefix="prostokvn-singbox-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            _download_file(url, archive, lambda t: emit(f"sing-box: {t}"))
            _verify_github_asset_digest(archive, asset)

            extracted = td_path / "extract"
            extracted.mkdir()
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extracted)

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
        emit(f"sing-box: установлен ({release.get('tag_name', 'latest')})")

    if install_xray:
        emit("Xray: получаю информацию о последнем официальном релизе...")
        release = _github_latest_release("XTLS/Xray-core")
        expected = "xray-windows-arm64-v8a.zip" if arch == "arm64" else "xray-windows-64.zip"
        asset = _find_release_asset(release, lambda n: n.lower() == expected)
        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("GitHub не вернул ссылку на Xray release asset.")

        with tempfile.TemporaryDirectory(prefix="prostokvn-xray-") as td:
            td_path = Path(td)
            archive = td_path / str(asset["name"])
            _download_file(url, archive, lambda t: emit(f"Xray: {t}"))
            _verify_github_asset_digest(archive, asset)

            extracted = td_path / "extract"
            extracted.mkdir()
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extracted)

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
        emit(f"Xray: установлен ({release.get('tag_name', 'latest')})")

    return result



def find_singbox_binary(explicit: str = "") -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file(): return p.resolve()
    env = os.environ.get("SINGBOX_EXE")
    if env and Path(env).is_file(): return Path(env).resolve()
    roots = [
        Path(r"C:\Program Files (x86)\v2rayN-windows-64"),
        Path(r"C:\Program Files\v2rayN-windows-64"),
        Path.home() / "Desktop" / "v2rayN-windows-64",
        APP_DIR,
    ]
    names = ["sing-box.exe", "sing-box-client.exe"]
    for root in roots:
        if not root.exists(): continue
        for name in names:
            p = root / "bin" / "sing_box" / name
            if p.is_file(): return p.resolve()
            p = root / name
            if p.is_file(): return p.resolve()
    for root in roots[:2]:
        if not root.exists(): continue
        try:
            for name in names:
                for p in root.glob(f"**/{name}"):
                    if p.is_file(): return p.resolve()
        except Exception:
            pass
    raise FileNotFoundError("Не найден sing-box.exe. ProstoKVN Network может установить официальный core автоматически.")


def find_xray_binary(explicit: str = "") -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file(): return p.resolve()
    env = os.environ.get("XRAY_EXE")
    if env and Path(env).is_file(): return Path(env).resolve()
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
        if not root.exists(): continue
        for rel in (Path("bin") / "xray" / "xray.exe", Path("bin") / "Xray" / "xray.exe", Path("xray.exe")):
            p = root / rel
            if p.is_file(): return p.resolve()
    for root in roots[:2]:
        if not root.exists(): continue
        try:
            for p in root.glob("**/xray.exe"):
                if p.is_file(): return p.resolve()
        except Exception:
            pass
    raise FileNotFoundError("Не найден xray.exe. ProstoKVN Network может установить официальный core автоматически.")


