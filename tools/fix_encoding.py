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


def has_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def repair_line(line: str) -> str:
    current = line

    # Some lines were damaged twice while a temporary workflow rewrote the file.
    # Two or three passes safely restore UTF-8; stop as soon as the text is clean.
    for _ in range(3):
        if not has_mojibake(current):
            break
        try:
            repaired = current.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if repaired == current:
            break
        current = repaired

    return current


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
