# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

TEXT_EXTENSIONS = {".py", ".pyw", ".md", ".json", ".yml", ".yaml", ".bat", ".txt"}
MOJIBAKE_MARKERS = ("Ð", "Ñ", "Â", "Ã")


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "build", "dist", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS:
            yield path


def check_utf8() -> None:
    broken = []

    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            broken.append(f"{path.relative_to(ROOT)}: не UTF-8")
            continue

        if any(marker in text for marker in MOJIBAKE_MARKERS):
            broken.append(f"{path.relative_to(ROOT)}: похоже на сломанную кодировку")

    if broken:
        raise RuntimeError("\n".join(broken))


def check_python_syntax() -> None:
    for path in SRC.rglob("*"):
        if path.suffix.lower() not in {".py", ".pyw"}:
            continue
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")


def read_app_version() -> str:
    tree = ast.parse((SRC / "app_config.py").read_text(encoding="utf-8"))

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "APP_VERSION":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value

    raise RuntimeError("APP_VERSION не найден в src/app_config.py")


def check_versions() -> None:
    meta = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    meta_version = str(meta.get("version") or "").strip()
    app_version = read_app_version()

    if not meta_version:
        raise RuntimeError("version.json не содержит version")
    if meta_version != app_version:
        raise RuntimeError(
            f"Версии не совпадают: version.json={meta_version}, app_config.py={app_version}"
        )

    version_info = (SRC / "version_info.txt").read_text(encoding="utf-8")
    if f"u'{app_version}'" not in version_info:
        raise RuntimeError("src/version_info.txt содержит другую версию")


def main() -> None:
    check_utf8()
    check_python_syntax()
    check_versions()
    print("Source check: OK")


if __name__ == "__main__":
    main()
