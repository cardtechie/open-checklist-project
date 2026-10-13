"""Unit tests for tools/check_work_order.py (stdlib unittest; fixtures built inline)."""
import copy
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_work_order as cwo  # noqa: E402

UUID = "a1e7c40a-d72f-47ca-860d-6d4f603b876f"

BLOCK = """<!-- ocp-discover:v1 -->
Resolved by Discover.

```yaml
name: 2025 Panini Prizm Draft Picks
genre: Sports
sports: [Football]
year: 2025
sources:
  - url: https://example.org/2025-prizm-draft-picks
    card_count: 100
    parallels_listed: true
```
"""


def comment(body, created="2026-10-01T00:00:00Z", assoc="MEMBER"):
    return {"body": body, "created_at": created, "author_association": assoc}


def ready_payload():
    return {
        "issue": {"number": 77, "state": "open", "title": "[Work Order] 2025 Panini Prizm Draft Picks (Football)",
                  "type": {"name": "Work Order"}, "labels": []},
        "field_values": [
            {"issue_field_id": 44649933, "issue_field_name": "set_id", "value": "2025-panini-prizm-draft-picks"},
            {"issue_field_id": 44650144, "issue_field_name": "Reserved set UUID", "value": UUID},
        ],
        "comments": [comment("unrelated"), comment(BLOCK)],
    }


class CheckWorkOrderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name) / "data"
        (self.data / "football").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self, payload):
        return cwo.check(payload, self.data)

    def assertNotReady(self, verdict, fragment):
        self.assertFalse(verdict["ready"])
        self.assertTrue(any(fragment in r for r in verdict["reasons"]),
                        f"{fragment!r} not in {verdict['reasons']}")

    def test_ready(self):
        v = self.run_check(ready_payload())
        self.assertTrue(v["ready"], v["reasons"])
        self.assertEqual(v["set_id"], "2025-panini-prizm-draft-picks")
        self.assertEqual(v["reserved_uuid"], UUID)
        self.assertEqual(v["name"], "2025 Panini Prizm Draft Picks")
        self.assertEqual(v["name_source"], "discover-block")
        self.assertEqual(v["sports"], ["Football"])
        self.assertEqual(v["year"], 2025)
        self.assertEqual(v["sources"], [{"url": "https://example.org/2025-prizm-draft-picks",
                                         "card_count": 100, "parallels_listed": True}])

    # --- item 1
    def test_wrong_type(self):
        p = ready_payload()
        p["issue"]["type"] = {"name": "Task"}
        self.assertNotReady(self.run_check(p), "issue type")

    def test_label_alone_is_not_enough(self):
        p = ready_payload()
        p["issue"]["type"] = None
        p["issue"]["labels"] = [{"name": "work-order"}]
        self.assertNotReady(self.run_check(p), "issue type")

    def test_closed(self):
        p = ready_payload()
        p["issue"]["state"] = "closed"
        self.assertNotReady(self.run_check(p), "not open")

    def test_pull_request(self):
        p = ready_payload()
        p["issue"]["pull_request"] = {"url": "x"}
        self.assertNotReady(self.run_check(p), "pull request")

    # --- item 2
    def test_missing_set_id(self):
        p = ready_payload()
        p["field_values"] = p["field_values"][1:]
        self.assertNotReady(self.run_check(p), "set_id is empty")

    def test_bad_slug(self):
        p = ready_payload()
        p["field_values"][0]["value"] = "2025 Panini Prizm"
        self.assertNotReady(self.run_check(p), "not a lowercase slug")

    def test_set_id_with_surrounding_whitespace_rejected(self):
        p = ready_payload()
        p["field_values"][0]["value"] = " 2025-panini-prizm-draft-picks "
        self.assertNotReady(self.run_check(p), "surrounding whitespace")

    def test_set_id_dir_collision(self):
        (self.data / "football" / "2025-panini-prizm-draft-picks").mkdir()
        self.assertNotReady(self.run_check(ready_payload()), "already has a data directory")

    def test_field_resolved_by_id_when_name_absent(self):
        p = ready_payload()
        for f in p["field_values"]:
            del f["issue_field_name"]
        self.assertTrue(self.run_check(p)["ready"])

    # --- item 3
    def test_missing_uuid(self):
        p = ready_payload()
        p["field_values"] = p["field_values"][:1]
        self.assertNotReady(self.run_check(p), "Reserved set UUID is empty")

    def test_bad_uuid(self):
        p = ready_payload()
        p["field_values"][1]["value"] = "not-a-uuid"
        self.assertNotReady(self.run_check(p), "not a valid UUID")

    def test_non_hyphenated_uuid_forms_rejected(self):
        for form in ("{" + UUID + "}", "urn:uuid:" + UUID, UUID.replace("-", "")):
            p = ready_payload()
            p["field_values"][1]["value"] = form
            self.assertNotReady(self.run_check(p), "not a valid UUID")

    def test_reserved_uuid_returned_unchanged(self):
        p = ready_payload()
        p["field_values"][1]["value"] = UUID.upper()
        v = self.run_check(p)
        self.assertTrue(v["ready"], v["reasons"])
        self.assertEqual(v["reserved_uuid"], UUID.upper())

    def test_uppercase_uuid_collides_with_lowercase(self):
        d = self.data / "football" / "other-set"
        d.mkdir(parents=True)
        (d / "set.yaml").write_text(f"uuid: {UUID}\n")
        p = ready_payload()
        p["field_values"][1]["value"] = UUID.upper()
        self.assertNotReady(self.run_check(p), "already used")

    def test_uuid_collision(self):
        d = self.data / "football" / "other-set" / "checklists"
        d.mkdir(parents=True)
        (d / "base.yaml").write_text(f"- number: '1'\n  uuid: {UUID.upper()}\n")
        self.assertNotReady(self.run_check(ready_payload()), "already used")

    # --- item 4
    def test_no_discover_block(self):
        p = ready_payload()
        p["comments"] = [comment("hello")]
        self.assertNotReady(self.run_check(p), "no discover block")

    def test_untrusted_discover_block_ignored(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, assoc="NONE")]
        self.assertNotReady(self.run_check(p), "owner, member or collaborator")

    def test_newest_block_wins(self):
        p = ready_payload()
        newer = BLOCK.replace("card_count: 100", "card_count: 110")
        p["comments"] = [comment(newer, "2026-10-05T00:00:00Z"), comment(BLOCK, "2026-10-01T00:00:00Z")]
        self.assertEqual(self.run_check(p)["sources"][0]["card_count"], 110)

    def test_newest_untrusted_block_does_not_override(self):
        p = ready_payload()
        evil = BLOCK.replace("https://example.org/", "https://evil.example/")
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         comment(evil, "2026-10-05T00:00:00Z", assoc="NONE")]
        v = self.run_check(p)
        self.assertTrue(v["ready"])
        self.assertIn("example.org", v["sources"][0]["url"])

    def test_stop_newer_than_block_revokes_it(self):
        p = ready_payload()
        stop = "<!-- ocp-discover-stop:v1 -->\nreason: source-disagreement\n\n**Discover stopped.**\n"
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"), comment(stop, "2026-10-05T00:00:00Z")]
        v = self.run_check(p)
        self.assertNotReady(v, "discover stopped (source-disagreement)")
        self.assertEqual(v["sources"], [])

    def test_stop_patched_after_block_revokes_it(self):
        # A re-run PATCHes its earlier stop in place: updated_at, not created_at, counts.
        p = ready_payload()
        stop = comment("<!-- ocp-discover-stop:v1 -->\nreason: api-mismatch\n", "2026-09-01T00:00:00Z")
        stop["updated_at"] = "2026-10-05T00:00:00Z"
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"), stop]
        self.assertNotReady(self.run_check(p), "discover stopped (api-mismatch)")

    def test_block_rewritten_after_stop_is_effective(self):
        p = ready_payload()
        block = comment(BLOCK, "2026-09-01T00:00:00Z")
        block["updated_at"] = "2026-10-05T00:00:00Z"
        p["comments"] = [block, comment("<!-- ocp-discover-stop:v1 -->\nreason: no-source\n",
                                        "2026-10-01T00:00:00Z")]
        self.assertTrue(self.run_check(p)["ready"])

    def test_rerun_patching_older_block_makes_it_effective(self):
        # Two trusted blocks; a re-run PATCHes the OLDER one, so it is the last written.
        p = ready_payload()
        older = comment(BLOCK.replace("card_count: 100", "card_count: 120"), "2026-09-01T00:00:00Z")
        older["updated_at"] = "2026-10-10T00:00:00Z"
        newer = comment(BLOCK, "2026-10-01T00:00:00Z")
        p["comments"] = [older, newer]
        v = self.run_check(p)
        self.assertTrue(v["ready"], v["reasons"])
        self.assertEqual(v["sources"][0]["card_count"], 120)

    def test_stop_older_than_patched_older_block_does_not_revoke(self):
        # The stop post-dates the newer block's creation but pre-dates the re-run
        # that PATCHed the older block, so the patched block is effective.
        p = ready_payload()
        older = comment(BLOCK.replace("card_count: 100", "card_count: 120"), "2026-09-01T00:00:00Z")
        older["updated_at"] = "2026-10-10T00:00:00Z"
        newer = comment(BLOCK, "2026-10-01T00:00:00Z")
        stop = comment("<!-- ocp-discover-stop:v1 -->\nreason: source-disagreement\n",
                       "2026-10-05T00:00:00Z")
        p["comments"] = [older, newer, stop]
        v = self.run_check(p)
        self.assertTrue(v["ready"], v["reasons"])
        self.assertEqual(v["sources"][0]["card_count"], 120)

    def test_untrusted_stop_does_not_revoke(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         comment("<!-- ocp-discover-stop:v1 -->\nreason: no-source\n",
                                 "2026-10-05T00:00:00Z", assoc="NONE")]
        self.assertTrue(self.run_check(p)["ready"])

    # --- reservation stops (ocp-reserve-stop:v1, written by the reserve workflow)
    RESERVE_STOP = ("<!-- ocp-reserve-stop:v1 -->\n\u23f8 **Identity not reserved** \u2014 the pinned "
                    "`Reserved set UUID` (`a`) differs from the Set UUID recorded in the body (`b`). "
                    "Nothing was written. Resolve it on the issue and re-run the workflow.")
    RESERVE_OK = "<!-- ocp-reserve:v1 -->\nrun: api-lookup\n\U0001f516 Reserved identity \u2014 `set_id`: `x`."
    RESERVE_OK_ISSUE_EVENT = ("<!-- ocp-reserve:v1 -->\nrun: issue-event\n\U0001f516 Identity confirmed "
                              "\u2014 `set_id`: `x`. Supersedes the earlier `ocp-reserve-stop:v1` comment.")
    RESERVE_OK_UNTAGGED = "<!-- ocp-reserve:v1 -->\n\U0001f516 Reserved identity \u2014 `set_id`: `x`."
    RESERVE_STOP_API = ("<!-- ocp-reserve-stop:v1 -->\nreason: api-uuid-mismatch\n\u23f8 **Identity not "
                        "reserved** \u2014 the pinned `Reserved set UUID` (`a`) differs from the Trading "
                        "Card API set's UUID (`c`). Nothing was written. Resolve it on the issue and "
                        "re-run the workflow.")

    @staticmethod
    def bot(body, created, updated=None):
        c = comment(body, created, assoc="NONE")
        c["user"] = {"login": "github-actions[bot]", "type": "Bot"}
        if updated:
            c["updated_at"] = updated
        return c

    def test_reserve_stop_newer_than_block_makes_not_ready(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z")]
        v = self.run_check(p)
        self.assertNotReady(v, "identity reservation stopped (the pinned `Reserved set UUID` (`a`) "
                               "differs from the Set UUID recorded in the body (`b`))")
        self.assertEqual(v["sources"], [])

    def test_reserve_stop_patched_after_block_makes_not_ready(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         self.bot(self.RESERVE_STOP, "2026-09-01T00:00:00Z", "2026-10-05T00:00:00Z")]
        self.assertNotReady(self.run_check(p), "identity reservation stopped")

    def test_reserve_stop_older_than_block_does_not_revoke(self):
        p = ready_payload()
        p["comments"] = [self.bot(self.RESERVE_STOP, "2026-09-01T00:00:00Z"),
                         comment(BLOCK, "2026-10-01T00:00:00Z")]
        self.assertTrue(self.run_check(p)["ready"])

    def test_discover_block_rewritten_after_reserve_stop_is_ready(self):
        p = ready_payload()
        block = comment(BLOCK, "2026-09-01T00:00:00Z")
        block["updated_at"] = "2026-10-10T00:00:00Z"
        p["comments"] = [block, self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z")]
        self.assertTrue(self.run_check(p)["ready"])

    def test_reservation_written_after_reserve_stop_is_ready(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z"),
                         self.bot(self.RESERVE_OK, "2026-09-01T00:00:00Z", "2026-10-06T00:00:00Z")]
        v = self.run_check(p)
        self.assertTrue(v["ready"], v["reasons"])
        self.assertEqual(v["sources"][0]["card_count"], 100)

    def test_issue_event_reservation_after_reserve_stop_does_not_clear_it(self):
        for ok in (self.RESERVE_OK_ISSUE_EVENT, self.RESERVE_OK_UNTAGGED):
            p = ready_payload()
            p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                             self.bot(self.RESERVE_STOP_API, "2026-10-05T00:00:00Z"),
                             self.bot(ok, "2026-09-01T00:00:00Z", "2026-10-06T00:00:00Z")]
            self.assertNotReady(self.run_check(p), "identity reservation stopped (api-uuid-mismatch: ")

    def test_api_mismatch_stop_then_label_event_then_matching_lookup(self):
        """The sequence the reserve workflow produces: a Discover dispatch stops on an API
        UUID mismatch, a later label event changes nothing (and must not be read as a
        clearing), then a Discover dispatch whose lookup matches rewrites the reserve
        comment as a lookup run."""
        block = comment(BLOCK, "2026-10-01T00:00:00Z")
        # Before any stop, an issue-event run had written its reserve comment.
        early = self.bot(self.RESERVE_OK_ISSUE_EVENT, "2026-09-01T00:00:00Z")
        stop = self.bot(self.RESERVE_STOP_API, "2026-10-05T00:00:00Z")
        p = ready_payload()
        p["comments"] = [early, block, stop]
        self.assertNotReady(self.run_check(p), "identity reservation stopped (api-uuid-mismatch: ")
        # A label event: even if a reserve comment from it were (wrongly) rewritten after
        # the stop, it is tagged issue-event and does not clear the stop.
        relabel = self.bot(self.RESERVE_OK_ISSUE_EVENT, "2026-09-01T00:00:00Z", "2026-10-06T00:00:00Z")
        p["comments"] = [relabel, block, stop]
        self.assertNotReady(self.run_check(p), "identity reservation stopped")
        # The matching lookup dispatch rewrites the same comment as a lookup run.
        cleared = self.bot(self.RESERVE_OK, "2026-09-01T00:00:00Z", "2026-10-07T00:00:00Z")
        p["comments"] = [cleared, block, stop]
        v = self.run_check(p)
        self.assertTrue(v["ready"], v["reasons"])

    def test_reservation_older_than_reserve_stop_does_not_clear_it(self):
        p = ready_payload()
        p["comments"] = [self.bot(self.RESERVE_OK, "2026-09-01T00:00:00Z"),
                         comment(BLOCK, "2026-10-01T00:00:00Z"),
                         self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z")]
        self.assertNotReady(self.run_check(p), "identity reservation stopped")

    def test_reserve_stop_from_trusted_member_counts(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         comment(self.RESERVE_STOP, "2026-10-05T00:00:00Z")]
        self.assertNotReady(self.run_check(p), "identity reservation stopped")

    def test_untrusted_reserve_stop_does_not_revoke(self):
        p = ready_payload()
        spoof = comment(self.RESERVE_STOP, "2026-10-05T00:00:00Z", assoc="NONE")
        spoof["user"] = {"login": "github-actions", "type": "User"}
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"), spoof]
        self.assertTrue(self.run_check(p)["ready"])

    def test_untrusted_reservation_does_not_clear_reserve_stop(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z"),
                         comment(self.RESERVE_OK, "2026-10-06T00:00:00Z", assoc="NONE")]
        self.assertNotReady(self.run_check(p), "identity reservation stopped")

    def test_reserve_stop_with_no_discover_block_reports_both(self):
        p = ready_payload()
        p["comments"] = [self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z")]
        v = self.run_check(p)
        self.assertNotReady(v, "identity reservation stopped")
        self.assertNotReady(v, "no discover block comment")

    def test_reserve_and_discover_stops_both_reported(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK, "2026-10-01T00:00:00Z"),
                         self.bot(self.RESERVE_STOP, "2026-10-05T00:00:00Z"),
                         comment("<!-- ocp-discover-stop:v1 -->\nreason: identity-conflict\n",
                                 "2026-10-06T00:00:00Z")]
        v = self.run_check(p)
        self.assertNotReady(v, "identity reservation stopped")
        self.assertNotReady(v, "discover stopped (identity-conflict)")

    def test_block_without_fenced_yaml(self):
        p = ready_payload()
        p["comments"] = [comment("<!-- ocp-discover:v1 -->\nsources: none here")]
        self.assertNotReady(self.run_check(p), "no fenced yaml")

    def test_malformed_yaml(self):
        p = ready_payload()
        p["comments"] = [comment("<!-- ocp-discover:v1 -->\n```yaml\nsources: [\n```\n")]
        self.assertNotReady(self.run_check(p), "malformed")

    def test_no_sources(self):
        p = ready_payload()
        p["comments"] = [comment("<!-- ocp-discover:v1 -->\n```yaml\nname: X\n```\n")]
        self.assertNotReady(self.run_check(p), "no sources")

    def test_bad_card_counts(self):
        for bad in ("0", "-3", "'100'", "true", "12.5"):
            p = ready_payload()
            p["comments"] = [comment(BLOCK.replace("card_count: 100", f"card_count: {bad}"))]
            self.assertNotReady(self.run_check(p), "card_count")

    def test_bad_url(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK.replace("https://example.org/2025-prizm-draft-picks",
                                               "ftp://example.org/x"))]
        self.assertNotReady(self.run_check(p), "not http/https")

    def test_malformed_bracketed_url_is_not_ready(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK.replace("https://example.org/2025-prizm-draft-picks", "http://[::1"))]
        self.assertNotReady(self.run_check(p), "not http/https")

    def test_non_public_source_hosts_rejected(self):
        for bad in ("http://localhost/x", "http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data/",
                    "http://10.0.0.5/x", "http://192.168.1.1/x", "http://[::1]/x", "http://[fd00::1]/x",
                    "http://2130706433/x", "http://0x7f.1/x", "http://metadata.google.internal/x",
                    "http://printer.local/x", "http://intranet/x", "https://user:pw@example.org/x",
                    "http://example.org:notaport/x"):
            p = ready_payload()
            p["comments"] = [comment(BLOCK.replace("https://example.org/2025-prizm-draft-picks", bad))]
            self.assertNotReady(self.run_check(p), "source 1 url")

    def test_public_source_hosts_accepted(self):
        for good in ("https://www.beckett.com/x", "http://93.184.216.34/x", "https://example.org:8443/x"):
            p = ready_payload()
            p["comments"] = [comment(BLOCK.replace("https://example.org/2025-prizm-draft-picks", good))]
            self.assertTrue(self.run_check(p)["ready"], good)

    def test_name_falls_back_to_title(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK.replace("name: 2025 Panini Prizm Draft Picks\n", ""))]
        v = self.run_check(p)
        self.assertTrue(v["ready"])
        self.assertEqual(v["name"], "2025 Panini Prizm Draft Picks (Football)")
        self.assertEqual(v["name_source"], "title")

    def test_bad_genre(self):
        p = ready_payload()
        p["comments"] = [comment(BLOCK.replace("genre: Sports", "genre: Football"))]
        self.assertNotReady(self.run_check(p), "genre must be one of")

    # --- CLI
    def test_cli_from_json_exit_codes(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "wo.json"
            f.write_text(json.dumps(ready_payload()))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cwo.main(["--from-json", str(f), "--data-dir", str(self.data)])
            self.assertEqual(rc, cwo.EXIT_READY)
            self.assertTrue(json.loads(buf.getvalue())["ready"])

            bad = copy.deepcopy(ready_payload())
            bad["comments"] = []
            f.write_text(json.dumps(bad))
            with redirect_stdout(io.StringIO()):
                rc = cwo.main(["--from-json", str(f), "--data-dir", str(self.data)])
            self.assertEqual(rc, cwo.EXIT_NOT_READY)

    def test_cli_usage_errors(self):
        with redirect_stdout(io.StringIO()), unittest.mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(cwo.main([]), cwo.EXIT_USAGE)
            self.assertEqual(cwo.main(["77", "--repo", "bad repo; rm -rf"]), cwo.EXIT_USAGE)
            self.assertEqual(cwo.main(["--from-json", "/nonexistent/x.json"]), cwo.EXIT_USAGE)
            with tempfile.TemporaryDirectory() as t:
                f = Path(t) / "bad-utf8.json"
                f.write_bytes(b'{"issue": {"title": "\xff\xfe"}}')
                self.assertEqual(cwo.main(["--from-json", str(f)]), cwo.EXIT_USAGE)


    def test_cli_malformed_github_json_is_read_error(self):
        cases = [
            ["not json", "[]", ""],                       # issue body
            ['{"number": 77}', "{oops", ""],               # field values
            ['{"number": 77}', "[]", '{"body": "ok"}\n{broken'],  # one paginated comment
            ['[]', "[]", ""],                               # issue is not an object
            ['{"number": 77}', "{}", ""],                   # field values not an array
            ['{"number": 77}', "[]", "[1, 2]"],             # comment is not an object
        ]
        for issue, fields, comments in cases:
            outs = iter([issue, fields, comments])
            with unittest.mock.patch.object(cwo, "_gh_json", side_effect=lambda args: next(outs)), \
                    redirect_stdout(io.StringIO()), unittest.mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(cwo.main(["77"]), cwo.EXIT_USAGE, (issue, fields, comments))

if __name__ == "__main__":
    unittest.main()
