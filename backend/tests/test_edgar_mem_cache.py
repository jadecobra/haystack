"""In-memory companyfacts cache cap and TTL (#97)."""

from __future__ import annotations

import unittest
from collections import OrderedDict
from unittest.mock import patch

from app import edgar


class MemCacheCapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = edgar._mem_cache
        self._cap = edgar._MEM_CACHE_MAX
        edgar._mem_cache = OrderedDict()
        edgar._MEM_CACHE_MAX = 4

    def tearDown(self) -> None:
        edgar._mem_cache = self._saved
        edgar._MEM_CACHE_MAX = self._cap

    def test_over_cap_drops_oldest_first(self) -> None:
        base = 1_700_000_000.0
        for i in range(6):
            edgar._mem_cache_put(f"{i:010d}", {"i": i}, now=base + i)

        self.assertEqual(len(edgar._mem_cache), 4)
        self.assertNotIn("0000000000", edgar._mem_cache)
        self.assertNotIn("0000000001", edgar._mem_cache)
        self.assertEqual(next(iter(edgar._mem_cache)), "0000000002")
        self.assertEqual(edgar._mem_cache["0000000005"][1], {"i": 5})

        # A read of the oldest survivor makes the next insert evict the one after it.
        self.assertEqual(edgar._mem_cache_get("0000000002", base + 10), {"i": 2})
        edgar._mem_cache_put("0000000006", {"i": 6}, now=base + 11)

        self.assertEqual(len(edgar._mem_cache), 4)
        self.assertNotIn("0000000003", edgar._mem_cache)
        self.assertEqual(edgar._mem_cache["0000000002"][1], {"i": 2})
        self.assertEqual(next(reversed(edgar._mem_cache)), "0000000006")

    def test_expired_entry_is_removed_and_not_returned(self) -> None:
        stored = 1_700_000_000.0
        edgar._mem_cache_put("0000320193", {"stale": True}, now=stored)
        fresh_at = stored + edgar._CACHE_TTL_S

        self.assertIsNone(edgar._mem_cache_get("0000320193", fresh_at))
        self.assertNotIn("0000320193", edgar._mem_cache)

    def test_write_purges_other_expired_entries(self) -> None:
        stored = 1_700_000_000.0
        edgar._mem_cache_put("0000000001", {"stale": True}, now=stored)
        edgar._mem_cache_put(
            "0000000002",
            {"ok": True},
            now=stored + edgar._CACHE_TTL_S + 1,
        )

        self.assertNotIn("0000000001", edgar._mem_cache)
        self.assertEqual(edgar._mem_cache["0000000002"][1], {"ok": True})

    def test_fetch_does_not_return_expired_memory_hit(self) -> None:
        key = "0000320193"
        edgar._mem_cache[key] = (
            1_700_000_000.0,
            {"entityName": "stale"},
        )
        disk = {"entityName": "Apple Inc."}
        with (
            patch("app.edgar.time.time", return_value=1_700_000_000.0 + edgar._CACHE_TTL_S + 5),
            patch("app.edgar._read_disk_cache", return_value=disk) as read_disk,
            patch("app.edgar._fetch_companyfacts_uncached") as network,
        ):
            meta: dict = {}
            got = edgar.fetch_companyfacts(key, meta=meta)

        self.assertEqual(got, disk)
        self.assertEqual(meta["cache_source"], "disk")
        self.assertEqual(edgar._mem_cache[key][1], disk)
        read_disk.assert_called_once_with(key)
        network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
