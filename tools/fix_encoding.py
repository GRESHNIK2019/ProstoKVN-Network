# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "src" / "ProstoKVNNetwork.pyw",
    ROOT / "src" / "app_config.py",
    ROOT / "src" / "updater.py",
    ROOT / "version.json",
    ROOT / "RELEASE_NOTES.md",
]

# UTF-8 text that was accidentally decoded as Windows-1252 usually contains
# these Latin characters. Normal Russian source text does not.
MOJIBAKE_MARKERS = ("\u00d0", "\u00d1", "\u00c2", "\u00c3")


def repair_line(line: str) -> str:
    if not any(marker in line for marker in MOJIBAKE_MARKERS):
        return line

    try:
        return line.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return line


def repair_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    repaired = "".join(repair_line(line) for line in original.splitlines(keepends=True))
    if repaired == original:
        return False

    path.write_text(repaired, encoding="utf-8")
    return True


def main() -> None:
    changed = []
    for path in FILES:
        if repair_file(path):
            changed.append(path.relative_to(ROOT))

    for path in changed:
        print(f"repaired: {path}")


if __name__ == "__main__":
    main()
