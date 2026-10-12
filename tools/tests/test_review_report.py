"""Unit tests for tools/review_report.py (stdlib unittest; fixtures built in temp dirs)."""
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_report as rr  # noqa: E402


def opts(**kw):
    base = dict(known_names=None, deceased=None, marquee=None, source_runs=None,
                famous_run=3, check_links=False)
    base.update(kw)
    return Namespace(**base)


def player(num, name):
    return {"number": num, "uuid": f"u-{num}",
            "subjects": [{"entities": [{"role": "player", "name": name}]}]}


def make_set(root, nodes, set_extra=None):
    """nodes: list of (node-dict, rows). Returns the set directory."""
    d = Path(root) / "s1"
    (d / "checklists").mkdir(parents=True)
    (d / "set.yaml").write_text(yaml.safe_dump({"set_id": "s1", **(set_extra or {})}))
    manifest = {"set_id": "s1", "base_sets": [n for n, _ in nodes]}
    (d / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    for node, rows in nodes:
        (d / "checklists" / f"{node['id']}.yaml").write_text(yaml.safe_dump(rows))
    return d


class ReviewReportTests(unittest.TestCase):
    def run_set(self, nodes, set_extra=None, **kw):
        with tempfile.TemporaryDirectory() as t:
            return rr.analyze_set(make_set(t, nodes, set_extra), opts(**kw))

    def test_declared_vs_actual_and_gaps(self):
        rep = self.run_set([({"id": "base", "declared_card_count": 5},
                             [player("1", "A"), player("2", "B"), player("5", "C")])])
        self.assertEqual(len(rep.findings["Declared vs actual count"]), 1)
        self.assertIn("missing 3 to 4", rep.findings["Numbering gaps"][0])

    def test_variation_nodes_skip_gap_check(self):
        rep = self.run_set([({"id": "v", "type": ["variation"]},
                             [player("1", "A"), player("9", "B")])])
        self.assertEqual(rep.findings["Numbering gaps"], [])

    def test_duplicate_numbers_and_subjects(self):
        rep = self.run_set([({"id": "base"}, [player("1", "A"), player("1", "B"), player("3", "C")])])
        self.assertEqual(len(rep.findings["Duplicate card numbers"]), 1)
        self.assertEqual(len(rep.findings["Duplicate subjects"]), 0)
        rep = self.run_set([({"id": "base"}, [player("1", "A"), player("2", "a")])])
        self.assertEqual(len(rep.findings["Duplicate subjects"]), 1)

    def test_rows_without_subjects_ignored(self):
        rep = self.run_set([({"id": "base"}, [{"number": "1"}, {"number": "2"}])])
        self.assertEqual(rep.findings["Duplicate subjects"], [])

    def test_parallel_consistency(self):
        node = {"id": "base", "parallels": [
            {"name": "Gold", "serial_numbered": True},
            {"name": "Blue", "print_run": 99},
            {"name": "Zero", "print_run": 0, "serial_numbered": True},
        ]}
        rep = self.run_set([(node, [player("1", "A")])])
        self.assertEqual(len(rep.findings["Parallel consistency"]), 3)

    def test_source_runs_global_and_per_node(self):
        node = {"id": "base", "parallels": [{"name": "Gold", "print_run": 50, "serial_numbered": True}]}
        rep = self.run_set([(node, [player("1", "A")])], source_runs={"Gold": 25})
        self.assertIn("vs source 25", rep.findings["Parallel consistency (vs source)"][0])
        self.assertEqual(rep.findings["Parallel consistency"], [])
        rep = self.run_set([(node, [player("1", "A")])], source_runs={"base": {"Gold": 50}})
        self.assertEqual(rep.findings["Parallel consistency (vs source)"], [])
        self.assertNotIn("Parallel consistency (vs source)", rep.skipped)

    def test_source_comparison_reported_as_skipped_not_zero(self):
        node = {"id": "base", "parallels": [{"name": "Gold", "print_run": 50, "serial_numbered": True}]}
        rep = self.run_set([(node, [player("1", "A")])])
        self.assertIn("Parallel consistency (vs source)", rep.skipped)
        row = next(l for l in rr.render([rep]).splitlines() if l.startswith("| Parallel consistency (vs source) |"))
        self.assertIn("skipped", row)

    def test_every_parallel_declaration_rendered(self):
        node = {"id": "base", "parallels": [
            {"name": "Gold", "print_run": 50, "serial_numbered": True},
            {"name": "Refractor"},
        ]}
        rep = self.run_set([(node, [player("1", "A")])], source_runs={"Gold": 50})
        self.assertEqual(rep.parallels, [("base", "Gold", 50, True, 50), ("base", "Refractor", None, None, None)])
        text = rr.render([rep])
        self.assertIn("### Parallels", text)
        self.assertIn("| `base` | Gold | 50 | yes | 50 |", text)
        self.assertIn("| `base` | Refractor | - | no | - |", text)

    def test_skipped_when_inputs_absent(self):
        rep = self.run_set([({"id": "base"}, [player("1", "A")])])
        for c in ("Never-seen names", "Deceased with live autograph", "Sequential famous player"):
            self.assertIn(c, rep.skipped)
            self.assertIn("skipped: no", rep.skipped[c])

    def test_never_seen_names(self):
        rep = self.run_set([({"id": "base"}, [player("1", "Known Guy"), player("2", "New Guy")])],
                           known_names={"known guy"})
        self.assertEqual(rep.findings["Never-seen names"], ["New Guy"])
        self.assertNotIn("Never-seen names", rep.skipped)

    def test_deceased_with_autograph(self):
        node = {"id": "au", "type": ["autograph"]}
        rep = self.run_set([(node, [player("1", "Late Player"), player("2", "Alive")])],
                           deceased={"late player"})
        self.assertEqual(len(rep.findings["Deceased with live autograph"]), 1)
        node = {"id": "ins", "type": ["insert"]}
        rep = self.run_set([(node, [player("1", "Late Player")])], deceased={"late player"})
        self.assertEqual(rep.findings["Deceased with live autograph"], [])

    def test_sequential_famous(self):
        rows = [player(str(i), n) for i, n in enumerate(["S1", "S2", "S3", "X", "S1"], 1)]
        rep = self.run_set([({"id": "base"}, rows)], marquee={"s1", "s2", "s3"})
        self.assertEqual(len(rep.findings["Sequential famous player"]), 1)

    def test_placeholder_urls(self):
        rep = self.run_set([({"id": "base"}, [player("1", "A")])],
                           set_extra={"description": "see https://example.com/x.jpg and https://real.org/ok"})
        self.assertEqual(len(rep.findings["Placeholder / dead URLs"]), 1)

    def test_malformed_set_does_not_crash(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "bad"
            d.mkdir()
            (d / "set.yaml").write_text("a: [unclosed")
            rep = rr.analyze_set(d, opts())
            self.assertTrue(rep.problems)
            self.assertIn("Review report", rr.render([rep]))

    def test_base_less_product_top_level_subsets(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "p"
            (d / "checklists").mkdir(parents=True)
            (d / "set.yaml").write_text("set_id: p\n")
            (d / "manifest.yaml").write_text(yaml.safe_dump(
                {"set_id": "p", "subsets": [{"id": "ins", "type": ["insert"]}]}))
            (d / "checklists" / "ins.yaml").write_text(yaml.safe_dump([player("1", "A")]))
            rep = rr.analyze_set(d, opts())
            self.assertEqual(rep.nodes[0][0], "ins")

    def test_gap_ranges_per_prefix(self):
        self.assertEqual(rr.gap_ranges(["A-1", "A-4", "B-1", "B-2"]), ["A-2 to A-3"])

    def test_empty_report(self):
        self.assertIn("No set directories", rr.render([]))


if __name__ == "__main__":
    unittest.main()
