"""Unit tests for tools/compare_sources.py (stdlib unittest; fixtures built inline)."""
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_work_order as cwo  # noqa: E402
import compare_sources as cs  # noqa: E402

URL_A = "https://example.org/2025-prizm-draft-picks"
URL_B = "https://checklists.example.com/prizm-dp-2025"
URL_C = "https://base-only.example.net/2025-prizm-dp"

CARDS = [{"number": "1", "name": "Cam Ward"},
         {"number": "2", "name": "Travis Hunter"},
         {"number": "10", "name": "Shedeur Sanders"}]
LADDER = [{"name": "Silver", "print_run": None},
          {"name": "Gold", "print_run": 10},
          {"name": "Green Shimmer", "print_run": 8}]


def sub(name, type_="autograph", count=40, listed=True):
    return {"name": name, "type": type_, "card_count": count, "parallels_listed": listed}


def source(url, cards=None, parallels=None, listed=True, count=None, subsets=None):
    cards = copy.deepcopy(CARDS if cards is None else cards)
    parallels = copy.deepcopy(LADDER if parallels is None else parallels) if listed else []
    return {"url": url, "card_count": len(cards) if count is None else count,
            "parallels_listed": listed, "cards": cards, "parallels": parallels,
            "subsets": copy.deepcopy(subsets or [])}


class Runner(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.n = 0

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, data, raw=None):
        self.n += 1
        p = self.dir / f"src{self.n}.yaml"
        p.write_text(raw if raw is not None else yaml.safe_dump(data, sort_keys=False))
        return str(p)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cs.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def assert_usage(self, *args):
        code, out, err = self.run_cli(*args)
        self.assertEqual(code, cs.EXIT_USAGE, err)
        self.assertEqual(out, "")
        payload = json.loads(err)
        self.assertIn("error", payload)
        self.assertIsInstance(payload["reasons"], list)
        return payload

    def differences(self, *datas):
        code, out, err = self.run_cli(*[self.write(d) for d in datas])
        self.assertEqual(code, cs.EXIT_DISAGREE, err)
        payload = json.loads(out)
        self.assertIs(payload["agree"], False)
        return payload["differences"]


class CompareSourcesList(Runner):
    def test_disagreement_lists_every_compared_source_even_when_values_are_sparse(self):
        # A and B are consistent; C states 3 but has 4 rows. The card_rows entry's
        # values hold C alone, so a ruling naming A could not be validated against it:
        # `sources` is the complete compared set (#91 recovery validates against it).
        extra = CARDS + [{"number": "11", "name": "Ashton Jeanty"}]
        paths = [self.write(source(URL_A)), self.write(source(URL_B)),
                 self.write(source(URL_C, cards=extra, count=3))]
        code, out, err = self.run_cli(*paths)
        self.assertEqual(code, cs.EXIT_DISAGREE, err)
        payload = json.loads(out)
        self.assertEqual(list(payload), ["agree", "sources", "differences"])
        self.assertEqual(payload["sources"], [URL_A, URL_B, URL_C])
        rows = [d for d in payload["differences"] if d["field"] == "card_rows"]
        self.assertEqual(rows, [{"field": "card_rows", "values": {URL_C: {"stated": 3, "rows": 4}}}])

    def test_base_only_source_is_listed_though_absent_from_parallels_values(self):
        paths = [self.write(source(URL_A)), self.write(source(URL_B, parallels=LADDER[:2])),
                 self.write(source(URL_C, listed=False))]
        code, out, err = self.run_cli(*paths)
        self.assertEqual(code, cs.EXIT_DISAGREE, err)
        payload = json.loads(out)
        self.assertEqual(payload["sources"], [URL_A, URL_B, URL_C])
        self.assertTrue(all(URL_C not in d["values"] for d in payload["differences"]))


class Agree(Runner):
    def test_two_agreeing_sources_print_a_block_the_checker_accepts(self):
        code, out, err = self.run_cli(self.write(source(URL_A)), self.write(source(URL_B)))
        self.assertEqual(code, cs.EXIT_AGREE, err)
        self.assertTrue(out.startswith(cwo.DISCOVER_MARKER + "\n"))
        reasons = []
        parsed = cwo.parse_discover(out, reasons)
        self.assertEqual(reasons, [])
        self.assertEqual(parsed["sources"], [
            {"url": URL_A, "card_count": 3, "parallels_listed": True},
            {"url": URL_B, "card_count": 3, "parallels_listed": True}])

    def test_whitespace_and_case_are_normalized(self):
        b = source(URL_B)
        b["cards"][0]["name"] = "  CAM   ward "
        b["parallels"][2]["name"] = "green  SHIMMER"
        code, _, err = self.run_cli(self.write(source(URL_A)), self.write(b))
        self.assertEqual(code, cs.EXIT_AGREE, err)

    def test_card_and_rung_order_do_not_matter(self):
        b = source(URL_B, cards=list(reversed(CARDS)), parallels=list(reversed(LADDER)))
        code, _, err = self.run_cli(self.write(source(URL_A)), self.write(b))
        self.assertEqual(code, cs.EXIT_AGREE, err)

    def test_base_only_source_is_left_out_of_the_ladder_comparison(self):
        code, out, err = self.run_cli(self.write(source(URL_A)), self.write(source(URL_C, listed=False)))
        self.assertEqual(code, cs.EXIT_AGREE, err)
        parsed = cwo.parse_discover(out, [])
        self.assertEqual([s["parallels_listed"] for s in parsed["sources"]], [True, False])

    def test_meta_is_emitted_and_round_trips(self):
        meta = self.write({"name": "2025 Panini Prizm Draft Picks", "genre": "Sports",
                           "sports": ["Football"], "category": ["Football"], "year": 2025})
        code, out, err = self.run_cli(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)
        self.assertEqual(code, cs.EXIT_AGREE, err)
        reasons = []
        parsed = cwo.parse_discover(out, reasons)
        self.assertEqual(reasons, [])
        self.assertEqual(parsed["name"], "2025 Panini Prizm Draft Picks")
        self.assertEqual(parsed["year"], 2025)
        self.assertNotIn("set_id", out)
        self.assertNotIn("uuid", out)


class Subsets(Runner):
    AUTO = sub("Rookie Autographs", "autograph", 40)
    INSERT = sub("Draft Class", "insert", 20, listed=False)

    def diffs(self, *srcs):
        code, out, err = self.run_cli(*[self.write(s) for s in srcs])
        self.assertEqual(code, cs.EXIT_DISAGREE, err)
        return json.loads(out)["differences"]

    def test_agreeing_subsets_are_emitted_and_round_trip_through_the_checker(self):
        a = source(URL_A, subsets=[self.AUTO, self.INSERT])
        b = source(URL_B, subsets=[sub("  rookie   AUTOGRAPHS", "autograph", 40), self.INSERT])
        code, out, err = self.run_cli(self.write(a), self.write(b))
        self.assertEqual(code, cs.EXIT_AGREE, err)
        reasons = []
        parsed = cwo.parse_discover(out, reasons)
        self.assertEqual(reasons, [])
        self.assertEqual(parsed["subsets"], [self.AUTO, self.INSERT])  # first spelling names it

    def test_base_only_product_emits_an_explicit_empty_list(self):
        code, out, err = self.run_cli(self.write(source(URL_A)), self.write(source(URL_B)))
        self.assertEqual(code, cs.EXIT_AGREE, err)
        self.assertIn("subsets: []", out)
        self.assertEqual(cwo.parse_discover(out, [])["subsets"], [])

    def test_parallels_listed_is_true_when_any_source_lists_the_ladder(self):
        a = source(URL_A, subsets=[sub("Rookie Autographs", "autograph", 40, listed=False)])
        b = source(URL_B, subsets=[sub("Rookie Autographs", "autograph", 40, listed=True)])
        code, out, err = self.run_cli(self.write(a), self.write(b))
        self.assertEqual(code, cs.EXIT_AGREE, err)
        self.assertTrue(cwo.parse_discover(out, [])["subsets"][0]["parallels_listed"])

    def test_a_source_listing_no_subsets_disagrees_with_one_that_does(self):
        diffs = self.diffs(source(URL_A, subsets=[self.AUTO]), source(URL_B))
        self.assertEqual(diffs, [{"field": "subsets", "name": "Rookie Autographs", "attribute": "listed",
                                  "values": {URL_A: True, URL_B: False}}])

    def test_subset_count_disagreement(self):
        diffs = self.diffs(source(URL_A, subsets=[self.AUTO]),
                           source(URL_B, subsets=[sub("Rookie Autographs", "autograph", 45)]))
        self.assertEqual(diffs, [{"field": "subsets", "name": "Rookie Autographs", "attribute": "card_count",
                                  "values": {URL_A: 40, URL_B: 45}}])

    def test_subset_type_disagreement(self):
        diffs = self.diffs(source(URL_A, subsets=[self.AUTO]),
                           source(URL_B, subsets=[sub("Rookie Autographs", "relic", 40)]))
        self.assertEqual([(d["attribute"], d["values"]) for d in diffs],
                         [("type", {URL_A: "autograph", URL_B: "relic"})])

    def test_malformed_subsets_are_exit_2(self):
        for bad in (sub("A", "parallel"), sub("A", count=0), sub("  "), {"name": "A", "type": "insert"}):
            with self.subTest(bad=bad):
                self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B, subsets=[bad])))
        dup = [sub("Rookie Autographs"), sub("rookie  autographs", "insert", 5)]
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B, subsets=dup)))

    def test_subsets_key_is_required(self):
        bad = source(URL_B)
        del bad["subsets"]
        self.assert_usage(self.write(source(URL_A)), self.write(bad))


class Disagree(Runner):
    def test_card_count(self):
        b = source(URL_B, cards=CARDS + [{"number": "11", "name": "Ashton Jeanty"}])
        diffs = self.differences(source(URL_A), b)
        self.assertEqual(diffs[0], {"field": "card_count", "values": {URL_A: 3, URL_B: 4}})
        self.assertEqual(diffs[1], {"field": "card_numbers", "number": "11",
                                    "values": {URL_A: False, URL_B: True}})

    def test_missing_rung_green_shimmer_case(self):
        # Work order #77: one source lists Green Shimmer /8, the other does not.
        b = source(URL_B, parallels=LADDER[:2])
        diffs = self.differences(source(URL_A), b)
        self.assertEqual(diffs, [{"field": "parallels", "name": "Green Shimmer", "print_run": 8,
                                  "values": {URL_A: True, URL_B: False}}])

    def test_print_run(self):
        b = source(URL_B)
        b["parallels"][1]["print_run"] = 5
        diffs = self.differences(source(URL_A), b)
        self.assertEqual([(d["field"], d["name"], d["print_run"]) for d in diffs],
                         [("parallels", "Gold", 5), ("parallels", "Gold", 10)])

    def test_card_name(self):
        b = source(URL_B)
        b["cards"][1]["name"] = "Travis Hunter Jr."
        diffs = self.differences(source(URL_A), b)
        self.assertEqual(diffs, [{"field": "card_names", "number": "2",
                                  "values": {URL_A: "Travis Hunter", URL_B: "Travis Hunter Jr."}}])

    def test_rows_differ_from_stated_count(self):
        b = source(URL_B, count=4)
        diffs = self.differences(source(URL_A), b)
        self.assertEqual(diffs[0]["field"], "card_count")
        self.assertEqual(diffs[1], {"field": "card_rows", "values": {URL_B: {"stated": 4, "rows": 3}}})

    def test_card_numbers_sort_naturally(self):
        extra = [{"number": n, "name": f"Player {n}"} for n in ("10a", "2", "100", "9")]
        a = source(URL_A, cards=[{"number": "1", "name": "Cam Ward"}] + extra, count=5)
        b = source(URL_B, cards=[{"number": "1", "name": "Cam Ward"}], count=5)
        diffs = [d["number"] for d in self.differences(a, b) if d["field"] == "card_numbers"]
        self.assertEqual(diffs, ["2", "9", "10a", "100"])

    def test_equal_natural_keys_sort_by_raw_number(self):
        extra = [{"number": n, "name": f"Player {n}"} for n in ("01", "001", "1")]
        a = source(URL_A, cards=extra, count=3)
        b = source(URL_B, cards=[], count=3)
        diffs = [d["number"] for d in self.differences(a, b) if d["field"] == "card_numbers"]
        self.assertEqual(diffs, ["001", "01", "1"])

    def test_non_decimal_digit_numbers_sort_without_crashing(self):
        extra = [{"number": n, "name": f"Player {n}"} for n in ("1\u00b2", "\u0662", "1")]
        a = source(URL_A, cards=extra, count=3)
        b = source(URL_B, cards=[], count=3)
        diffs = [d["number"] for d in self.differences(a, b) if d["field"] == "card_numbers"]
        self.assertEqual(diffs, ["1", "1\u00b2", "\u0662"])

    def test_three_sources_in_input_order(self):
        c = source(URL_C)
        c["card_count"] = 9
        diffs = self.differences(source(URL_A), source(URL_B), c)
        self.assertEqual(list(diffs[0]["values"]), [URL_A, URL_B, URL_C])


class Malformed(Runner):
    def test_missing_key(self):
        bad = source(URL_B)
        del bad["card_count"]
        self.assert_usage(self.write(source(URL_A)), self.write(bad))

    def test_wrong_type(self):
        bad = source(URL_B)
        bad["cards"][0]["number"] = 1
        payload = self.assert_usage(self.write(source(URL_A)), self.write(bad))
        self.assertTrue(any("cards/0/number" in r for r in payload["reasons"]))

    def test_boolean_card_count(self):
        bad = source(URL_B)
        bad["card_count"] = True
        self.assert_usage(self.write(source(URL_A)), self.write(bad))

    def test_parallels_present_when_not_listed(self):
        bad = source(URL_B)
        bad["parallels_listed"] = False
        self.assert_usage(self.write(source(URL_A)), self.write(bad))

    def test_unknown_key(self):
        bad = source(URL_B)
        bad["set_id"] = "x"
        self.assert_usage(self.write(source(URL_A)), self.write(bad))

    def test_bad_url(self):
        for url in ("http://localhost/x", "ftp://example.org/x", "http://10.0.0.1/x"):
            with self.subTest(url=url):
                self.assert_usage(self.write(source(URL_A)), self.write(source(url)))

    def test_whitespace_only_values_are_rejected(self):
        for field in ("card name", "card number", "parallel name"):
            with self.subTest(field=field):
                a, b = source(URL_A), source(URL_B)
                for src in (a, b):
                    if field == "card name":
                        src["cards"][0]["name"] = "   "
                    elif field == "card number":
                        src["cards"][0]["number"] = " \t "
                    else:
                        src["parallels"][0]["name"] = "  "
                self.assert_usage(self.write(a), self.write(b))

    def test_duplicate_card_number(self):
        cards = CARDS + [{"number": "2", "name": "Someone Else"}]
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B, cards=cards)))

    def test_duplicate_parallel(self):
        ladder = LADDER + [{"name": "gold", "print_run": 10}]
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B, parallels=ladder)))

    def test_duplicate_source_url(self):
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_A)))

    def test_duplicate_source_url_ignores_surrounding_whitespace(self):
        self.assert_usage(self.write(source(URL_A)), self.write(source(f"  {URL_A} ")))

    def test_unreadable_yaml(self):
        self.assert_usage(self.write(source(URL_A)), self.write(None, raw="url: [unterminated\n"))

    def test_missing_file(self):
        self.assert_usage(self.write(source(URL_A)), str(self.dir / "nope.yaml"))

    def test_single_input_file(self):
        self.assert_usage(self.write(source(URL_A)))

    def test_no_input_files(self):
        self.assert_usage()

    def test_unknown_flag_is_structured_usage_error(self):
        payload = self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--bogus")
        self.assertTrue(any("--bogus" in r for r in payload["reasons"]))

    def test_meta_without_value_is_structured_usage_error(self):
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta")

    def test_help_exits_zero(self):
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("usage", out)

    def test_meta_invalid_year(self):
        meta = self.write({"year": "2025-26"})
        payload = self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)
        self.assertTrue(any("year" in r for r in payload["reasons"]))

    def test_meta_invalid_year_even_when_sources_disagree(self):
        meta = self.write({"year": 0})
        b = source(URL_B, count=4)
        self.assert_usage(self.write(source(URL_A)), self.write(b), "--meta", meta)

    def test_meta_unknown_key(self):
        meta = self.write({"set_id": "2025-prizm"})
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)


class LoaderEdges(Runner):
    """Inputs that made the YAML loader or the writer raise instead of exiting 2."""

    def good_yaml(self, url=URL_A):
        return yaml.safe_dump(source(url), sort_keys=False)

    def assert_source_usage(self, raw):
        return self.assert_usage(self.write(None, raw=raw), self.write(source(URL_B)))

    def test_integer_past_the_digit_limit(self):
        huge = "9" * 5000
        for field in ("card_count", "print_run"):
            with self.subTest(field=field):
                raw = self.good_yaml().replace("card_count: 3", f"card_count: {huge}", 1) \
                    if field == "card_count" else self.good_yaml().replace("print_run: 10", f"print_run: {huge}", 1)
                self.assertIn(huge, raw)
                self.assert_source_usage(raw)

    def test_impossible_date(self):
        self.assert_source_usage(self.good_yaml() + "released: 2025-02-30\n")

    def test_nesting_past_the_recursion_limit(self):
        self.assert_source_usage("deep: " + "[" * 50000 + "]" * 50000 + "\n")

    def test_hex_integer_past_the_digit_limit(self):
        raw = self.good_yaml().replace("card_count: 3", "card_count: 0x" + "f" * 5000, 1)
        payload = self.assert_source_usage(raw)
        self.assertEqual(payload["reasons"], [f"card_count: larger than {cs.MAX_SAFE_INT}"])

    def test_count_above_the_json_safe_maximum(self):
        bad = source(URL_B, count=2 ** 53)
        self.assert_usage(self.write(source(URL_A)), self.write(bad))

    def test_meta_hex_year_that_cannot_be_written(self):
        meta = self.write(None, raw="year: 0x" + "f" * 5000 + "\n")
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)

    def test_meta_nested_too_deep_to_write(self):
        meta = self.write(None, raw="name: " + "[" * 400 + "x" + "]" * 400 + "\n")
        payload = self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)
        self.assertEqual(payload["reasons"], [f"nested deeper than {cs.MAX_DEPTH} levels"])

    def test_meta_value_that_yaml_rewrites(self):
        meta = self.write({"name": "2025 Prizm\u0085Draft Picks"})
        payload = self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)
        self.assertEqual(payload["error"], "a --meta value does not survive the Discover block unchanged")

    def test_meta_impossible_date(self):
        meta = self.write(None, raw="year: 2025-02-30\n")
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B)), "--meta", meta)

    def test_card_number_with_a_digit_run_past_the_limit(self):
        long_number = "1" * 5000
        a = source(URL_A, cards=CARDS + [{"number": long_number, "name": "Long"}], count=4)
        diffs = [d["number"] for d in self.differences(a, source(URL_B, count=4))
                 if d["field"] == "card_numbers"]
        self.assertEqual(diffs, [long_number])

    def test_digit_runs_still_sort_by_value(self):
        self.assertLess(cs.natural_key("9"), cs.natural_key("10"))
        self.assertLess(cs.natural_key("10"), cs.natural_key("1" * 5000))
        self.assertEqual(cs.natural_key("002"), cs.natural_key("\u0662"))


class Schema(unittest.TestCase):
    def test_schema_is_a_valid_draft_2020_12_schema(self):
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(cs.load_schema())


if __name__ == "__main__":
    unittest.main()
