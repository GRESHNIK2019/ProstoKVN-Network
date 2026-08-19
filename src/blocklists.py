# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
import time
import urllib.request
from typing import Any, Callable

from app_config import APP_VERSION
from paths import BLOCKLIST_DIR, BLOCKLIST_META_PATH

BLOCKLIST_MAX_BYTES = 32 * 1024 * 1024
MIN_DOMAIN_ENTRIES = 20
MIN_SERVICE_ENTRIES = 2
MIN_SRS_BYTES = 32

ITDOG_DOMAIN_URLS = [
    "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Russia/inside-raw.lst",
    "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Russia/inside-raw.lst",
]
RUNETFREEDOM_DOMAIN_URLS = [
    "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geosite/release/ru-blocked.txt",
    "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geosite@release/ru-blocked.txt",
]
ITDOG_SERVICE_SOURCES = {
    "youtube": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/youtube.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/youtube.lst",
    ],
    "discord": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/discord.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/discord.lst",
    ],
    "meta": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/meta.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/meta.lst",
    ],
    "twitter": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/twitter.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/twitter.lst",
    ],
    "tiktok": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/tiktok.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/tiktok.lst",
    ],
    "telegram": [
        "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/telegram.lst",
        "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/telegram.lst",
    ],
}
YOUTUBE_FALLBACK = """
youtube.com
ytimg.com
yting.com
ggpht.com
googlevideo.com
youtubekids.com
youtu.be
yt.be
youtube-nocookie.com
wide-youtube.l.google.com
ytimg.l.google.com
youtubei.googleapis.com
youtubeembeddedplayer.googleapis.com
youtube-ui.l.google.com
yt-video-upload.l.google.com
jnn-pa.googleapis.com
yt3.googleusercontent.com
"""
RUNETFREEDOM_IP_SOURCES = {
    "ru_blocked_ip": [
        "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/ru-blocked.srs",
        "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/ru-blocked.srs",
    ],
    "ru_blocked_community_ip": [
        "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/ru-blocked-community.srs",
        "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/ru-blocked-community.srs",
    ],
    "re_filter_ip": [
        "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/re-filter.srs",
        "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/re-filter.srs",
    ],
}


def _download_any(
    urls: list[str],
    timeout: float = 25.0,
    max_bytes: int = BLOCKLIST_MAX_BYTES,
) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for url in urls:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"ProstoKVNNetwork/{APP_VERSION}",
                    "Accept": "*/*",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                declared = int(response.headers.get("Content-Length") or 0)
                if declared > max_bytes:
                    raise RuntimeError(f"сервер объявил слишком большой файл: {declared} байт")
                data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise RuntimeError(f"файл превышает лимит {max_bytes} байт")
            if not data:
                raise RuntimeError("сервер вернул пустой файл")
            return data, url
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"не удалось скачать список: {last_error}")


def _normalize_domain_list(text: str) -> tuple[set[str], set[str], set[str], set[str]]:
    exact: set[str] = set()
    suffix: set[str] = set()
    regexes: set[str] = set()
    keywords: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!", "//")):
            continue

        low = line.lower()
        if low.startswith("domain:"):
            value = line[7:].strip().strip(".").lower()
            if value:
                suffix.add(value)
        elif low.startswith("full:"):
            value = line[5:].strip().strip(".").lower()
            if value:
                exact.add(value)
        elif low.startswith("regexp:"):
            value = line[7:].strip()
            if value:
                regexes.add(value)
        elif low.startswith("keyword:"):
            value = line[8:].strip()
            if value:
                keywords.add(value)
        else:
            value = line.split()[0].strip().strip(".").lower()
            if value and " " not in value and "/" not in value and ":" not in value:
                suffix.add(value)

    return exact, suffix, regexes, keywords


def _domain_entry_count(text: str) -> int:
    exact, suffix, regexes, keywords = _normalize_domain_list(text)
    return len(exact) + len(suffix) + len(regexes) + len(keywords)


def _validated_domain_text(data: bytes, minimum: int, label: str) -> str:
    text = data.decode("utf-8", errors="replace")
    count = _domain_entry_count(text)
    if count < minimum:
        raise RuntimeError(f"{label}: в списке подозрительно мало записей ({count})")
    return text


def _chunked(values: list[str], size: int = 6000) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _build_domain_ruleset(texts: list[str], destination: Path) -> dict[str, int]:
    exact: set[str] = set()
    suffix: set[str] = set()
    regexes: set[str] = set()
    keywords: set[str] = set()

    for text in texts:
        current_exact, current_suffix, current_regexes, current_keywords = _normalize_domain_list(text)
        exact.update(current_exact)
        suffix.update(current_suffix)
        regexes.update(current_regexes)
        keywords.update(current_keywords)

    exact.difference_update(suffix)
    rules: list[dict[str, Any]] = []
    for chunk in _chunked(sorted(suffix)):
        rules.append({"domain_suffix": chunk})
    for chunk in _chunked(sorted(exact)):
        rules.append({"domain": chunk})
    for chunk in _chunked(sorted(regexes), 1500):
        rules.append({"domain_regex": chunk})
    for chunk in _chunked(sorted(keywords), 1500):
        rules.append({"domain_keyword": chunk})

    if not rules:
        raise RuntimeError("Новый доменный rule-set пуст; старый кэш не заменён.")

    payload = {"version": 3, "rules": rules}
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(destination)
    return {
        "suffix": len(suffix),
        "exact": len(exact),
        "regex": len(regexes),
        "keyword": len(keywords),
    }


def _load_previous_meta() -> dict[str, Any]:
    try:
        data = json.loads(BLOCKLIST_META_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_cached_ru_blocklists() -> list[Path]:
    paths = [BLOCKLIST_DIR / "ru_domains.json", BLOCKLIST_DIR / "service_domains.json"]
    paths += [BLOCKLIST_DIR / f"{name}.srs" for name in RUNETFREEDOM_IP_SOURCES]
    return [path for path in paths if path.is_file() and path.stat().st_size > 0]


def blocklists_age_seconds() -> float | None:
    try:
        data = _load_previous_meta()
        updated_at = float(data.get("updated_at", 0))
        return max(0.0, time.time() - updated_at) if updated_at else None
    except Exception:
        return None


def update_ru_blocklists(log: Callable[[str], None] | None = None) -> dict[str, Any]:
    def emit(message: str) -> None:
        if not log:
            return
        try:
            log(message)
        except Exception:
            pass

    previous_meta = _load_previous_meta()
    used_sources: list[str] = []
    domain_errors: list[str] = []
    domain_texts: list[str] = []

    domain_sources = (
        ("ITDog Russia inside", ITDOG_DOMAIN_URLS),
        ("RunetFreedom ru-blocked", RUNETFREEDOM_DOMAIN_URLS),
    )
    for label, urls in domain_sources:
        try:
            data, used = _download_any(urls)
            text = _validated_domain_text(data, MIN_DOMAIN_ENTRIES, label)
            domain_texts.append(text)
            used_sources.append(used)
            emit(f"Список {label}: загружен ({_domain_entry_count(text)} записей)")
        except Exception as exc:
            domain_errors.append(f"{label}: {exc}")
            emit(f"Список {label}: ошибка загрузки ({exc})")

    domain_path = BLOCKLIST_DIR / "ru_domains.json"
    previous_counts = previous_meta.get("counts")
    counts = previous_counts if isinstance(previous_counts, dict) else {"suffix": 0, "exact": 0, "regex": 0, "keyword": 0}
    domain_complete = len(domain_texts) == len(domain_sources)
    if domain_complete or (domain_texts and not domain_path.exists()):
        counts = _build_domain_ruleset(domain_texts, domain_path)
    elif domain_path.exists() and domain_path.stat().st_size > 0:
        emit("Доменные списки: обновление неполное, сохраняю предыдущий кэш")
    elif domain_texts:
        counts = _build_domain_ruleset(domain_texts, domain_path)
    else:
        raise RuntimeError(
            "Не удалось получить доменные списки РФ и локального кэша ещё нет. "
            + "; ".join(domain_errors)
        )

    service_texts: list[str] = []
    service_errors: list[str] = []
    service_loaded: list[str] = []
    for service, urls in ITDOG_SERVICE_SOURCES.items():
        try:
            data, used = _download_any(urls)
            text = _validated_domain_text(data, MIN_SERVICE_ENTRIES, f"service {service}")
            service_texts.append(text)
            service_loaded.append(service)
            used_sources.append(used)
            emit(f"Сервис {service}: загружен ({_domain_entry_count(text)} доменов)")
        except Exception as exc:
            service_errors.append(f"{service}: {exc}")
            emit(f"Сервис {service}: ошибка загрузки ({exc})")

    service_path = BLOCKLIST_DIR / "service_domains.json"
    previous_service_counts = previous_meta.get("service_counts")
    service_counts = previous_service_counts if isinstance(previous_service_counts, dict) else {"suffix": 0, "exact": 0, "regex": 0, "keyword": 0}
    services_complete = len(service_loaded) == len(ITDOG_SERVICE_SOURCES)
    try:
        if services_complete:
            service_counts = _build_domain_ruleset([YOUTUBE_FALLBACK] + service_texts, service_path)
        elif service_path.exists() and service_path.stat().st_size > 0:
            # Не заменяем хороший полный кэш урезанным набором только потому,
            # что один из внешних источников временно недоступен.
            emit("Сервисные домены: обновление неполное, сохраняю предыдущий кэш")
        else:
            service_counts = _build_domain_ruleset([YOUTUBE_FALLBACK] + service_texts, service_path)
    except Exception as exc:
        service_errors.append(f"service ruleset: {exc}")
        if service_path.exists() and service_path.stat().st_size > 0:
            emit("Сервисные домены: используется предыдущий локальный кэш")
        else:
            raise

    ip_paths: list[Path] = []
    ip_errors: list[str] = []
    ip_updated = 0
    for name, urls in RUNETFREEDOM_IP_SOURCES.items():
        destination = BLOCKLIST_DIR / f"{name}.srs"
        try:
            data, used = _download_any(urls)
            if len(data) < MIN_SRS_BYTES:
                raise RuntimeError(f"SRS-файл подозрительно мал ({len(data)} байт)")
            temp = destination.with_suffix(".srs.tmp")
            temp.write_bytes(data)
            temp.replace(destination)
            used_sources.append(used)
            ip_paths.append(destination)
            ip_updated += 1
            emit(f"IP rule-set {name}: обновлён ({len(data) // 1024} КБ)")
        except Exception as exc:
            ip_errors.append(f"{name}: {exc}")
            if destination.exists() and destination.stat().st_size >= MIN_SRS_BYTES:
                ip_paths.append(destination)
                emit(f"IP rule-set {name}: используется кэш")
            else:
                emit(f"IP rule-set {name}: недоступен ({exc})")

    paths: list[Path] = []
    if domain_path.exists() and domain_path.stat().st_size > 0:
        paths.append(domain_path)
    if service_path.exists() and service_path.stat().st_size > 0:
        paths.append(service_path)
    paths.extend(ip_paths)

    all_errors = domain_errors + service_errors + ip_errors
    complete = domain_complete and services_complete and ip_updated == len(RUNETFREEDOM_IP_SOURCES)
    now = time.time()
    previous_updated_at = float(previous_meta.get("updated_at") or 0.0)
    updated_at = now if complete else previous_updated_at

    meta = {
        "updated_at": updated_at,
        "attempted_at": now,
        "updated_local": time.strftime("%Y-%m-%d %H:%M:%S") if complete else str(previous_meta.get("updated_local") or ""),
        "complete": complete,
        "counts": counts,
        "service_counts": service_counts,
        "services": service_loaded if services_complete else list(previous_meta.get("services") or service_loaded),
        "paths": [str(path) for path in paths],
        "sources": used_sources,
        "errors": all_errors,
    }
    try:
        temp_meta = BLOCKLIST_META_PATH.with_suffix(".json.tmp")
        temp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_meta.replace(BLOCKLIST_META_PATH)
    except Exception:
        pass
    return meta
