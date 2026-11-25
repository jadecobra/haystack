"""Docs must quote LOCKED_LABELS and not revive dropped stack claims."""

import os
import re
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.main import AnalysisResponse, PeerRow, app
from app.metrics import LOCKED_LABELS, SCHEMA_VERSION
from app.peer_metrics import ROW_KEYS

ROOT = Path(__file__).resolve().parents[2]
SPEC = (ROOT / "spec.md").read_text()
README = (ROOT / "README.md").read_text()
LOCKED_LABELS_TS = (ROOT / "frontend" / "lib" / "locked-labels.ts").read_text()
METRICS_CATALOG_TS = (
    ROOT / "frontend" / "lib" / "metrics-catalog.ts"
).read_text()

BANNED_IN_SPEC = (
    "AWS Lambda",
    "ElastiCache",
    "API Gateway",
    "CloudFront",
    "ao start",
)
BANNED_IN_README = ("ao start", "AWS Lambda")


def _ts_string_literals(text: str) -> list[str]:
    return re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text)


class TestDocsContract(unittest.TestCase):
    def test_spec_lists_every_locked_label(self):
        missing = [label for label in LOCKED_LABELS if label not in SPEC]
        self.assertEqual(missing, [])

    def test_spec_label_order_matches_contract(self):
        listed = [
            line[2:].strip()
            for line in SPEC.splitlines()
            if line.startswith("- ") and line[2:].strip() in LOCKED_LABELS
        ]
        self.assertEqual(listed, list(LOCKED_LABELS))

    def test_spec_omits_dropped_stack(self):
        hits = [phrase for phrase in BANNED_IN_SPEC if phrase in SPEC]
        self.assertEqual(hits, [])

    def test_readme_omits_dropped_stack(self):
        hits = [phrase for phrase in BANNED_IN_README if phrase in README]
        self.assertEqual(hits, [])

    def test_readme_does_not_fork_the_label_list(self):
        listed = [label for label in LOCKED_LABELS if label in README]
        self.assertEqual(
            listed,
            [],
            "README must not copy LOCKED_LABELS; point at contract instead",
        )

    def test_frontend_locked_labels_match_contract(self):
        listed = _ts_string_literals(LOCKED_LABELS_TS)
        self.assertEqual(listed, list(LOCKED_LABELS))

    def test_metrics_catalog_labels_match_contract(self):
        listed = re.findall(r'label:\s*"([^"]+)"', METRICS_CATALOG_TS)
        self.assertEqual(listed, list(LOCKED_LABELS))

    def test_analysis_response_cik_is_optional(self):
        field = AnalysisResponse.model_fields["cik"]
        self.assertFalse(field.is_required())
        self.assertIsNone(field.default)

    def test_analyze_fixture_returns_cik_string(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            response = TestClient(app).get("/analyze/AAPL")
        self.assertEqual(response.status_code, 200)
        cik = response.json().get("cik")
        self.assertIsInstance(cik, str)
        self.assertTrue(cik)

    def test_main_red_issue_watches_real_workflows(self):
        wf_dir = ROOT / ".github" / "workflows"
        actual_names: set[str] = set()
        for wf_path in wf_dir.glob("*.yml"):
            for line in wf_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("name:"):
                    actual_names.add(line.split("name:", 1)[1].strip().strip("\"'"))
                    break
        main_red_text = (wf_dir / "main-red-issue.yml").read_text(encoding="utf-8")
        match = re.search(r"^\s*workflows:\s*\[([^\]]+)\]", main_red_text, re.MULTILINE)
        self.assertIsNotNone(match)
        watched = _ts_string_literals(match.group(1))
        missing = [name for name in watched if name not in actual_names]
        self.assertEqual(missing, [])
        self.assertIn("S&P 1500 GICS map refresh", watched)
        self.assertIn("US ICB taxonomy refresh", watched)

    def test_peer_row_keys_match_pydantic_model(self):
        self.assertEqual(set(ROW_KEYS), set(PeerRow.model_fields) - {"current", "missing"})

    def test_verify_haystack_http_matches_schema_version_and_row_count(self):
        http_helper = (
            ROOT / ".cursor" / "skills" / "verify-haystack" / "helpers" / "http"
        ).read_text(encoding="utf-8")
        self.assertIn(f'"schema_version":"{SCHEMA_VERSION}"', http_helper)
        self.assertIn(f'"row_count":{len(LOCKED_LABELS)}', http_helper)
