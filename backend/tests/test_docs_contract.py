"""Docs must quote LOCKED_LABELS and not revive dropped stack claims."""

from pathlib import Path
import unittest

from app.metrics import LOCKED_LABELS

ROOT = Path(__file__).resolve().parents[2]
SPEC = (ROOT / "spec.md").read_text()
README = (ROOT / "README.md").read_text()

BANNED_IN_SPEC = (
    "AWS Lambda",
    "ElastiCache",
    "API Gateway",
    "CloudFront",
    "ao start",
)
BANNED_IN_README = ("ao start", "AWS Lambda")


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
