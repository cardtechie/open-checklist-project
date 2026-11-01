"""Unit tests for the category-vs-sports check in tools/validate.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate as v  # noqa: E402


class CategoryRepeatsSportTests(unittest.TestCase):
    def test_equal_values_flagged(self):
        self.assertEqual(v.category_repeats_sport({"category": ["Baseball"], "sports": ["Baseball"]}), ["Baseball"])

    def test_case_insensitive_match_flagged(self):
        self.assertEqual(v.category_repeats_sport({"category": ["football"], "sports": ["Football"]}), ["football"])

    def test_league_passes(self):
        self.assertEqual(v.category_repeats_sport({"category": ["MLB"], "sports": ["Baseball"]}), [])

    def test_missing_or_non_list_fields_do_not_crash(self):
        for doc in (None, {}, {"category": "MLB", "sports": ["Baseball"]},
                    {"category": ["MLB"], "sports": None}, {"category": [1], "sports": [2]}):
            self.assertEqual(v.category_repeats_sport(doc), [])


if __name__ == "__main__":
    unittest.main()
