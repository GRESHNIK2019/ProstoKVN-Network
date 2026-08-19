# -*- coding: utf-8 -*-
from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import blocklists


class FakeResponse:
    def __init__(self, data: bytes, declared: int | None = None):
        self._stream = io.BytesIO(data)
        self.headers = {}
        if declared is not None:
            self.headers["Content-Length"] = str(declared)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class BlocklistSafetyTests(unittest.TestCase):
    def test_download_rejects_declared_oversize(self):
        response = FakeResponse(b"small", declared=101)
        with mock.patch.object(blocklists.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "слишком большой"):
                blocklists._download_any(["https://example.test/list"], max_bytes=100)

    def test_download_rejects_stream_larger_than_limit_without_content_length(self):
        response = FakeResponse(b"x" * 101)
        with mock.patch.object(blocklists.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "превышает лимит"):
                blocklists._download_any(["https://example.test/list"], max_bytes=100)

    def test_domain_sanity_rejects_tiny_response(self):
        with self.assertRaisesRegex(RuntimeError, "подозрительно мало"):
            blocklists._validated_domain_text(b"example.com\n", 20, "test")

    def test_ruleset_replacement_is_atomic_and_nonempty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            counts = blocklists._build_domain_ruleset(
                ["one.example\ntwo.example\nthree.example\n"],
                path,
            )
            self.assertTrue(path.is_file())
            self.assertEqual(counts["suffix"], 3)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_empty_ruleset_does_not_replace_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text('{"old":true}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "пуст"):
                blocklists._build_domain_ruleset(["# comments only\n"], path)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"old":true}')


if __name__ == "__main__":
    unittest.main()
