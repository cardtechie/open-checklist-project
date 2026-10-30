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


def source(url, cards=None, parallels=None, listed=True, count=None):
    cards = copy.deepcopy(CARDS if cards is None else cards)
    parallels = copy.deepcopy(LADDER if parallels is None else parallels) if listed else []
    return {"url": url, "card_count": len(cards) if count is None else count,
            "parallels_listed": listed, "cards": cards, "parallels": parallels}


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

    def test_duplicate_card_number(self):
        cards = CARDS + [{"number": "2", "name": "Someone Else"}]
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B, cards=cards)))

    def test_duplicate_parallel(self):
        ladder = LADDER + [{"name": "gold", "print_run": 10}]
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_B, parallels=ladder)))

    def test_duplicate_source_url(self):
        self.assert_usage(self.write(source(URL_A)), self.write(source(URL_A)))

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


class Schema(unittest.TestCase):
    def test_schema_is_a_valid_draft_2020_12_schema(self):
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(cs.load_schema())


if __name__ == "__main__":
    unittest.main()
