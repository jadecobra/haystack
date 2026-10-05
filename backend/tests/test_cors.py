"""CORS allow-list: apex + isolated verify ports; www redirects to apex."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from app.main import _cors_origins


class TestCorsOrigins(unittest.TestCase):
    def test_apex_and_verify_ports_allowed_www_dropped(self):
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": ""}):
            origins = _cors_origins()
        self.assertIn("https://longmuch.com", origins)
        self.assertNotIn("https://www.longmuch.com", origins)
        for port in range(3457, 3465):
            self.assertIn(f"http://127.0.0.1:{port}", origins)
            self.assertIn(f"http://localhost:{port}", origins)
        self.assertNotIn("http://127.0.0.1:3000", origins)


if __name__ == "__main__":
    unittest.main()
