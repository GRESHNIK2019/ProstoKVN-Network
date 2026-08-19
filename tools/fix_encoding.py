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

# Признаки строки, где UTF-8 по ошибке прочитали как однобайтовую кодировку.
MOJIBAKE_MARKERS = ("Ð", "Ñ", "Â", "Ã", "â")


def mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS)


def restore_original_bytes(text: str) -> bytes:
    """Восстанавливает байты после ошибочного декодирования UTF-8 как CP1252."""
    result = bytearray()

    for char in text:
        try:
            encoded = char.encode("cp1252")
            if len(encoded) == 1:
                result.extend(encoded)
                continue
        except UnicodeEncodeError:
            pass

        # Неопределённые в CP1252 байты иногда остаются как C1-control символы.
        code = ord(char)
        if code <= 0xFF:
            result.append(code)
            continue

        raise UnicodeEncodeError("cp1252", char, 0, 1, "character cannot be restored")

    return bytes(result)


def repair_line(line: str) -> str:
    current = line

    for _ in range(3):
        before = mojibake_score(current)
        if before == 0:
            break

        try:
            repaired = restore_original_bytes(current).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break

        if mojibake_score(repaired) >= before:
            break
        current = repaired

    return current


def repair_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    repaired = "".join(repair_line(line) for line in original.splitlines(keepends=True))

    if repaired == original:
        return False

    path.write_text(repaired, encoding="utf-8", newline="\n")
    return True


def main() -> None:
    changed: list[Path] = []

    for path in FILES:
        if path.exists() and repair_file(path):
            changed.append(path.relative_to(ROOT))

    for path in changed:
        print(f"repaired: {path}")


if __name__ == "__main__":
    main()
