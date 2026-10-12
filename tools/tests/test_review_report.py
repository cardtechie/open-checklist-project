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

    def test_table_cells_escape_pipes_and_newlines(self):
        node = {"id": "base", "parallels": [{"name": "Gold | Foil\nShimmer", "print_run": 5, "serial_numbered": True}]}
        text = rr.render([self.run_set([(node, [player("1", "A")])])])
        self.assertIn("| `base` | Gold \\| Foil Shimmer | 5 | yes | - |", text)

    def test_dead_link_row_partial_without_check_links(self):
        rep = self.run_set([({"id": "base"}, [player("1", "A")])])
        self.assertIn("Placeholder / dead URLs", rep.partial)
        row = next(l for l in rr.render([rep]).splitlines() if l.startswith("| Placeholder / dead URLs |"))
        self.assertIn("0 (partial)", row)

    def test_source_runs_must_be_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "runs.yaml"
            f.write_text("- 50\n- 25\n")
            with self.assertRaises(SystemExit):
                rr.main([t, "--source-runs", str(f)])
            f.write_text("Gold: 50\n")
            self.assertEqual(rr.load_source_runs(str(f)), ({"Gold": 50}, None))

    def test_famous_run_below_one_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            for bad in ("0", "-2"):
                with self.assertRaises(SystemExit):
                    rr.main([t, "--marquee", __file__, "--famous-run", bad])

    def test_node_id_outside_checklists_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "s"
            (d / "checklists").mkdir(parents=True)
            (Path(t) / "other.yaml").write_text(yaml.safe_dump([player("1", "Leaked")]))
            (d / "set.yaml").write_text("set_id: s\n")
            (d / "manifest.yaml").write_text(yaml.safe_dump(
                {"set_id": "s", "base_sets": [{"id": "../../other"}, {"id": "Bad_Id"}]}))
            rep = rr.analyze_set(d, opts(known_names=set()))
            self.assertEqual(rep.nodes, [])
            self.assertEqual(rep.findings["Never-seen names"], [])
            self.assertEqual(sum("not a valid slug" in p for p in rep.problems), 2)

    def test_malformed_manifest_types_recorded_not_raised(self):
        for manifest in ({"base_sets": 1},
                         {"base_sets": [{"id": "base", "subsets": 1, "type": 1, "parallels": 3}]}):
            with tempfile.TemporaryDirectory() as t:
                d = Path(t) / "s"
                (d / "checklists").mkdir(parents=True)
                (d / "set.yaml").write_text("set_id: s\n")
                (d / "manifest.yaml").write_text(yaml.safe_dump(manifest))
                (d / "checklists" / "base.yaml").write_text(yaml.safe_dump(
                    [{"number": "1", "subjects": 1}, {"number": "2", "subjects": [{"entities": 5}]}]))
                rep = rr.analyze_set(d, opts())
                self.assertTrue(rep.problems)
                self.assertIn("Review report", rr.render([rep]))

    def test_sequential_famous_requires_consecutive_numbers(self):
        rows = [player("1", "S1"), player("3", "S2"), player("4", "S3")]
        rep = self.run_set([({"id": "base"}, rows)], marquee={"s1", "s2", "s3"})
        self.assertEqual(rep.findings["Sequential famous player"], [])
        rows = [player("3", "S1"), player("4", "S2"), player("5", "S3")]
        rep = self.run_set([({"id": "base"}, rows)], marquee={"s1", "s2", "s3"})
        self.assertEqual(len(rep.findings["Sequential famous player"]), 1)

    def test_untrusted_values_escaped_in_findings(self):
        rep = self.run_set([({"id": "base"}, [player("1", "## Heading\n<img src=x>")])],
                           known_names=set())
        text = rr.render([rep])
        self.assertNotIn("\n## Heading", text)
        self.assertNotIn("<img", text.replace("\\<img", ""))  # only the escaped form survives
        self.assertIn("\\#\\# Heading \\<img src=x\\>", text)

    def test_probe_falls_back_to_get_and_flags_restricted(self):
        import urllib.error
        calls = []

        def fake(url, method):
            calls.append(method)
            codes = {"HEAD": 405, "GET": 200} if "a" in url else {"HEAD": 403, "GET": 403}
            if codes[method] >= 400:
                raise urllib.error.HTTPError(url, codes[method], "x", {}, None)
            return codes[method]

        orig = rr._request
        rr._request = fake
        try:
            self.assertIsNone(rr.probe("https://a.test/"))
            self.assertEqual(calls, ["HEAD", "GET"])
            self.assertEqual(rr.probe("https://b.test/"), ("restricted", "HTTP 403"))
        finally:
            rr._request = orig

    def test_empty_report(self):
        self.assertIn("No set directories", rr.render([]))


if __name__ == "__main__":
    unittest.main()
