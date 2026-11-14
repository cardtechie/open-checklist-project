"""Tests for the `base: false` (parallel-only row) coverage check in tools/validate.py
(stdlib unittest; fixtures built in temp dirs)."""
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate as v  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
U3 = "33333333-3333-4333-8333-333333333333"
SET_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
NODE_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def schemas():
    sd = REPO / "schemas"
    return {k: v.load_schema(sd / k / "schema.yaml") for k in ("set", "manifest", "checklist")}


def run_set(rows, parallels, sections=None):
    """Write a one-node set and return the validator's error list."""
    with tempfile.TemporaryDirectory() as root:
        d = Path(root) / "s1"
        (d / "checklists").mkdir(parents=True)
        (d / "set.yaml").write_text(yaml.safe_dump({
            "set_id": "s1", "uuid": SET_UUID, "name": "S1", "genre": "Sports",
            "category": ["NFL"], "manufacturer": "M",
            "source": {"name": "Test", "url": "https://example.com"}}))
        node = {"id": "n1", "uuid": NODE_UUID, "name": "N1", "parallels": parallels}
        if sections:
            node["sections"] = sections
        (d / "manifest.yaml").write_text(yaml.safe_dump({"set_id": "s1", "base_sets": [node]}))
        (d / "checklists" / "n1.yaml").write_text(yaml.safe_dump(rows))
        rep = v.Report()
        v.validate_v03(d, schemas(), rep)
        return rep.errors


def base_false_errors(errors):
    return [e for e in errors if "base: false" in e]


class ParallelCoversTest(unittest.TestCase):
    def test_default_covers_all(self):
        self.assertTrue(v.parallel_covers("all", "1", []))
        self.assertTrue(v.parallel_covers(None, "1", []))

    def test_numbers_and_except(self):
        self.assertTrue(v.parallel_covers({"numbers": ["1"]}, "1", []))
        self.assertFalse(v.parallel_covers({"numbers": ["2"]}, "1", []))
        self.assertFalse(v.parallel_covers({"except": ["1"]}, "1", []))
        self.assertTrue(v.parallel_covers({"except": ["2"]}, "1", []))

    def test_sections(self):
        secs = [{"id": "a", "numbers": ["1"]}, {"id": "b", "numbers": ["2"]}]
        self.assertTrue(v.parallel_covers({"sections": ["a"]}, "1", secs))
        self.assertFalse(v.parallel_covers({"sections": ["b"]}, "1", secs))


class BaseFalseValidationTest(unittest.TestCase):
    def test_covered_by_parallel_passes(self):
        errors = run_set([{"number": "1", "uuid": U1, "base": False}], [{"name": "Gold"}])
        self.assertEqual(errors, [])

    def test_no_parallels_fails(self):
        errors = run_set([{"number": "1", "uuid": U1, "base": False}], [])
        self.assertEqual(len(base_false_errors(errors)), 1, errors)

    def test_excluded_by_except_fails(self):
        errors = run_set([{"number": "1", "uuid": U1, "base": False}],
                         [{"name": "Gold", "applies_to": {"except": ["1"]}}])
        self.assertEqual(len(base_false_errors(errors)), 1, errors)

    def test_covered_via_sections_passes(self):
        rows = [{"number": "1", "uuid": U1, "base": False}, {"number": "2", "uuid": U2}]
        sections = [{"id": "a", "name": "A", "numbers": ["1"]}, {"id": "b", "name": "B", "numbers": ["2"]}]
        errors = run_set(rows, [{"name": "Gold", "applies_to": {"sections": ["a"]}}], sections)
        self.assertEqual(errors, [])

    def test_not_covered_via_sections_fails(self):
        rows = [{"number": "1", "uuid": U1, "base": False}, {"number": "2", "uuid": U2}]
        sections = [{"id": "a", "name": "A", "numbers": ["1"]}, {"id": "b", "name": "B", "numbers": ["2"]}]
        errors = run_set(rows, [{"name": "Gold", "applies_to": {"sections": ["b"]}}], sections)
        self.assertEqual(len(base_false_errors(errors)), 1, errors)

    def test_default_rows_unaffected(self):
        errors = run_set([{"number": "1", "uuid": U1}, {"number": "2", "uuid": U2, "base": True}], [])
        self.assertEqual(errors, [])

    def test_non_boolean_base_is_schema_error(self):
        errors = run_set([{"number": "1", "uuid": U1, "base": "no"}], [{"name": "Gold"}])
        self.assertTrue(any("schema" in e and "base" in e for e in errors), errors)

    def test_only_uncovered_row_reported(self):
        rows = [{"number": "1", "uuid": U1, "base": False},
                {"number": "2", "uuid": U2, "base": False},
                {"number": "3", "uuid": U3}]
        errors = run_set(rows, [{"name": "Gold", "applies_to": {"numbers": ["1"]}}])
        be = base_false_errors(errors)
        self.assertEqual(len(be), 1, errors)
        self.assertIn("card 2", be[0])


if __name__ == "__main__":
    unittest.main()
