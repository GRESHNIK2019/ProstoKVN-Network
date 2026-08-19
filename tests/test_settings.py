# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from security import protect_text, unprotect_text
from settings_store import load_settings, save_settings
from subscriptions import dump_subscriptions, load_subscriptions, new_subscription


class SettingsTests(unittest.TestCase):
    def test_atomic_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_settings(path, {"value": 123})
            self.assertEqual(load_settings(path)["value"], 123)

    def test_backup_is_used_when_main_file_is_broken(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            backup = Path(directory) / "settings.json.bak"
            path.write_text("{broken", encoding="utf-8")
            backup.write_text(json.dumps({"restored": True}), encoding="utf-8")
            self.assertTrue(load_settings(path)["restored"])

    def test_subscription_migration_from_legacy_settings(self):
        items, active = load_subscriptions({
            "subscription_name": "legacy",
            "subscription_url": "https://example.test/sub",
            "subscription_enabled": True,
        })
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "legacy")
        self.assertEqual(items[0].url, "https://example.test/sub")
        self.assertEqual(active, items[0].id)

    def test_subscription_dump_roundtrip(self):
        item = new_subscription("one", "https://example.test/sub")
        raw = dump_subscriptions([item])
        loaded, active = load_subscriptions({"subscriptions": raw, "active_subscription_id": item.id})
        self.assertEqual(loaded[0].url, item.url)
        self.assertEqual(active, item.id)

    def test_protected_text_roundtrip(self):
        value = "https://example.test/private"
        protected = protect_text(value)
        self.assertNotEqual(protected, value)
        self.assertEqual(unprotect_text(protected), value)


if __name__ == "__main__":
    unittest.main()
