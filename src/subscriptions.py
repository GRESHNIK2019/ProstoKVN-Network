# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
import time
import uuid
from typing import Any

from security import protect_text, unprotect_text


@dataclass
class Subscription:
    id: str
    name: str
    url: str = ""
    enabled: bool = True
    update_interval: str = "0"
    sort_order: str = "1"
    last_update: float = 0.0


def new_subscription(name: str = "Новая подписка", url: str = "") -> Subscription:
    return Subscription(
        id=uuid.uuid4().hex[:12],
        name=(name or "Новая подписка").strip(),
        url=(url or "").strip(),
    )


def _load_item(raw: dict[str, Any]) -> Subscription | None:
    try:
        sub_id = str(raw.get("id") or uuid.uuid4().hex[:12])
        name = str(raw.get("name") or "Подписка").strip() or "Подписка"
        url = unprotect_text(str(raw.get("url") or ""))
        enabled = bool(raw.get("enabled", True))
        interval = str(raw.get("update_interval") or "0")
        sort_order = str(raw.get("sort_order") or "1")
        last_update = float(raw.get("last_update") or 0.0)
    except Exception:
        return None

    return Subscription(
        id=sub_id,
        name=name,
        url=url,
        enabled=enabled,
        update_interval=interval,
        sort_order=sort_order,
        last_update=last_update,
    )


def load_subscriptions(settings: dict[str, Any]) -> tuple[list[Subscription], str]:
    subscriptions: list[Subscription] = []
    raw_items = settings.get("subscriptions")

    if isinstance(raw_items, list):
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item = _load_item(raw)
            if item:
                subscriptions.append(item)

    # Миграция настроек v0.21 и старше.
    if not subscriptions:
        legacy_url = str(settings.get("subscription_url") or "")
        legacy = new_subscription(
            str(settings.get("subscription_name") or "import_sub"),
            legacy_url,
        )
        legacy.enabled = bool(settings.get("subscription_enabled", True))
        legacy.update_interval = str(settings.get("subscription_interval") or "0")
        legacy.sort_order = str(settings.get("subscription_sort") or "1")
        subscriptions.append(legacy)

    active_id = str(settings.get("active_subscription_id") or "")
    if not any(item.id == active_id for item in subscriptions):
        active_id = subscriptions[0].id

    return subscriptions, active_id


def dump_subscriptions(items: list[Subscription]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        result.append({
            "id": item.id,
            "name": item.name,
            "url": protect_text(item.url),
            "enabled": bool(item.enabled),
            "update_interval": str(item.update_interval or "0"),
            "sort_order": str(item.sort_order or "1"),
            "last_update": float(item.last_update or 0.0),
        })
    return result


def touch_subscription(item: Subscription) -> None:
    item.last_update = time.time()
