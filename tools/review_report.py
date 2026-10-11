#!/usr/bin/env python3
"""Computed review report for Open Checklist Project sets.

Derives a one-page markdown report from a set's set.yaml, manifest.yaml and
checklists/*.yaml so a human reviewer can judge a conversion without reading ~70 YAML
files. The report is ADVISORY and computed on demand: nothing it emits is committed, and
`tools/validate.py` remains the pass/fail gate for schema and IDENTITY.md invariants.

Exit code is 0 whenever a report was produced (findings never fail the run); non-zero
only for bad arguments or a crash.

Usage:
    python tools/review_report.py data/baseball/2026-bowman [more set dirs ...]
    python tools/review_report.py --changed-against origin/main

Optional input files enable checks that need data this repository does not hold. Without
one, that check prints an explicit "skipped" line instead of silently passing:
    --known-names FILE   one player name per line (e.g. an index exported from tcapi)
    --deceased FILE      one name per line; an optional ",date" suffix is ignored
    --marquee FILE       one famous-player name per line
    --source-runs FILE   YAML/JSON {parallel: print_run} or {node-id: {parallel: print_run}}
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import iter_nodes, find_dupes, _split  # noqa: E402

LIST_CAP = 10          # items shown inline before the rest fold into <details>
DETAIL_CAP = 200       # hard cap on items listed at all
LINK_CAP = 25          # max distinct URLs probed with --check-links
URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+")
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "localhost", "127.0.0.1",
    "via.placeholder.com", "placehold.co", "placeholder.com", "picsum.photos",
    "lorempixel.com", "dummyimage.com", "fakeimg.pl",
)
PLACEHOLDER_WORDS = ("placeholder", "your-", "todo", "tbd", "xxx", "/null", "/undefined", "/none")

CHECKS = [
    "Declared vs actual count", "Parallel consistency", "Numbering gaps",
    "Duplicate card numbers", "Duplicate subjects", "Placeholder / dead URLs",
    "Never-seen names", "Deceased with live autograph", "Sequential famous player",
]


def load_yaml(path):
    """Load YAML defensively. Returns (data, error-string-or-None)."""
    try:
        with open(path) as f:
            return yaml.safe_load(f), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except yaml.YAMLError as e:
        return None, f"invalid YAML in {path}: {str(e).splitlines()[0] if str(e) else e}"
    except OSError as e:
        return None, f"cannot read {path}: {e}"


def read_names(path):
    """One name per line; '#' comments and an optional ',extra' CSV tail are ignored."""
    names = set()
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].split(",", 1)[0].strip()
        if line:
            names.add(norm(line))
    return names


def norm(name):
    return " ".join(str(name).lower().split())


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def is_placeholder_url(url):
    low = url.lower()
    host = re.sub(r"^https?://", "", low).split("/", 1)[0].split(":", 1)[0]
    if any(host == h or host.endswith("." + h) for h in PLACEHOLDER_HOSTS):
        return True
    return any(w in low for w in PLACEHOLDER_WORDS)


def probe(url):
    """HEAD a URL; returns an error string for a dead link, or None if it responds OK."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ocp-review-report"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return None if r.status < 400 else f"HTTP {r.status}"
    except Exception as e:  # noqa: BLE001 - any failure is a finding
        return str(getattr(e, "code", None) or type(e).__name__)


def row_players(row):
    out = []
    for s in row.get("subjects") or []:
        if not isinstance(s, dict):
            continue
        for e in s.get("entities") or []:
            if isinstance(e, dict) and e.get("role") == "player" and e.get("name"):
                out.append(str(e["name"]))
    return out


def subject_key(row):
    subs = []
    for s in row.get("subjects") or []:
        if isinstance(s, dict):
            ents = tuple(sorted((str(e.get("role")), norm(e.get("name")))
                                for e in (s.get("entities") or [])
                                if isinstance(e, dict) and e.get("name")))
            if ents:
                subs.append(ents)
    return tuple(sorted(subs)) or None


def gap_ranges(numbers):
    """Missing integers per non-numeric prefix, compressed to 'PFX a-b' ranges."""
    by_prefix = defaultdict(set)
    for n in numbers:
        pfx, val = _split(n)
        if val is not None:
            by_prefix[pfx].add(val)
    out = []
    for pfx, vals in sorted(by_prefix.items(), key=lambda kv: str(kv[0])):
        lo, hi = min(vals), max(vals)
        start = None
        for i in range(lo, hi + 2):
            missing = i <= hi and i not in vals
            if missing and start is None:
                start = i
            elif not missing and start is not None:
                end = i - 1
                out.append(f"{pfx}{start}" if start == end else f"{pfx}{start} to {pfx}{end}")
                start = None
    return out


class SetReport:
    def __init__(self, set_dir):
        self.dir = Path(set_dir)
        self.problems = []                                  # load problems, shown at the top
        self.findings = {c: [] for c in CHECKS}             # check -> [str]
        self.skipped = {}                                   # check -> reason
        self.nodes = []                                     # per-node table rows

    def add(self, check, text):
        self.findings[check].append(text)


def analyze_set(set_dir, opts):
    rep = SetReport(set_dir)
    set_yaml, err = load_yaml(rep.dir / "set.yaml")
    if err:
        rep.problems.append(err)
    manifest, err = load_yaml(rep.dir / "manifest.yaml")
    if err:
        rep.problems.append(err)
    if not isinstance(manifest, dict):
        rep.problems.append("manifest.yaml is not a mapping; structural checks skipped")
        manifest = {}
    all_docs = [d for d in (set_yaml, manifest) if d is not None]

    seen_names = set()
    nodes_rows = {}
    for node, is_base in iter_nodes(manifest):
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            rep.problems.append("a node has no usable id; skipped")
            continue
        rows, err = load_yaml(rep.dir / "checklists" / f"{nid}.yaml")
        if err:
            rep.problems.append(err)
            rows = []
        if not isinstance(rows, list):
            rows = []
        rows = [r for r in rows if isinstance(r, dict)]
        all_docs.append(rows)
        nodes_rows[nid] = rows
        numbers = [str(r["number"]) for r in rows if r.get("number") is not None]
        parallels = [p for p in (node.get("parallels") or []) if isinstance(p, dict)]
        for r in rows:
            seen_names.update(norm(n) for n in row_players(r))

        # Structure: declared vs actual (shown, not re-gated; validate.py owns the error)
        dcc = node.get("declared_card_count")
        mark = ""
        if isinstance(dcc, int) and dcc != len(rows):
            mark = " (mismatch)"
            rep.add("Declared vs actual count", f"`{nid}`: declared {dcc}, found {len(rows)}")
        rep.nodes.append((nid, "base" if is_base else ",".join(map(str, node.get("type") or [])) or "subset",
                          "-" if dcc is None else str(dcc), str(len(rows)) + mark, str(len(parallels))))

        # Parallels: local consistency
        for p in parallels:
            name, run, ser = p.get("name", "<unnamed>"), p.get("print_run"), p.get("serial_numbered")
            if ser and run is None:
                rep.add("Parallel consistency", f"`{nid}` / {name}: serial_numbered without print_run")
            if run is not None and not ser:
                rep.add("Parallel consistency", f"`{nid}` / {name}: print_run {run} but not serial_numbered")
            if run == 0:
                rep.add("Parallel consistency", f"`{nid}` / {name}: print_run is 0")

        # Variation nodes are sparse by nature (a subset of the base numbers), so a gap
        # there is expected, not a finding.
        is_variation = "variation" in [str(t).lower() for t in (node.get("type") or [])]
        gaps = [] if is_variation else gap_ranges(numbers)
        if gaps:
            rep.add("Numbering gaps", f"`{nid}`: missing {', '.join(gaps[:8])}" + (" ..." if len(gaps) > 8 else ""))
        dn = find_dupes(numbers)
        if dn:
            rep.add("Duplicate card numbers", f"`{nid}`: {', '.join(sorted(dn)[:10])}")

        by_key = defaultdict(list)
        for r in rows:
            k = subject_key(r)
            if k is not None:
                by_key[k].append(str(r.get("number")))
        for k, nums in by_key.items():
            if len(nums) > 1:
                who = "; ".join(" + ".join(n for _, n in s) for s in k)
                rep.add("Duplicate subjects", f"`{nid}`: {who} on {', '.join(nums[:6])}")

        # Sequential famous player / deceased autograph (input-file driven)
        if opts.marquee is not None:
            run_ = []
            def flush():
                if len(run_) >= opts.famous_run:
                    rep.add("Sequential famous player",
                            f"`{nid}`: {len(run_)} consecutive marquee rows {run_[0][0]}..{run_[-1][0]}")
            for r in rows:
                ps = row_players(r)
                if ps and all(norm(p) in opts.marquee for p in ps):
                    run_.append((r.get("number"), ps))
                else:
                    flush()
                    run_ = []
            flush()
        if opts.deceased is not None and any("autograph" in str(t).lower() for t in (node.get("type") or [])):
            for r in rows:
                hit = [p for p in row_players(r) if norm(p) in opts.deceased]
                if hit:
                    rep.add("Deceased with live autograph", f"`{nid}` {r.get('number')}: {', '.join(hit)}")

    # Placeholder / dead URLs: every string in all three file kinds
    urls = {}
    for doc in all_docs:
        for s in walk_strings(doc):
            for u in URL_RE.findall(s):
                urls[u.rstrip(".,;")] = True
    for u in urls:
        if is_placeholder_url(u):
            rep.add("Placeholder / dead URLs", f"placeholder-looking URL: {u}")
    if opts.check_links:
        for u in list(urls)[:LINK_CAP]:
            if not is_placeholder_url(u):
                bad = probe(u)
                if bad:
                    rep.add("Placeholder / dead URLs", f"dead link ({bad}): {u}")
        if len(urls) > LINK_CAP:
            rep.add("Placeholder / dead URLs", f"link probe capped at {LINK_CAP} of {len(urls)} URLs")

    # Never-seen names
    if opts.known_names is None:
        rep.skipped["Never-seen names"] = "skipped: no --known-names input supplied"
    else:
        unseen = sorted({n for rows in nodes_rows.values() for r in rows for n in row_players(r)
                         if norm(n) not in opts.known_names})
        for n in unseen:
            rep.add("Never-seen names", n)
    if opts.deceased is None:
        rep.skipped["Deceased with live autograph"] = "skipped: no --deceased input supplied"
    if opts.marquee is None:
        rep.skipped["Sequential famous player"] = "skipped: no --marquee input supplied"

    # Source-declared print runs
    if opts.source_runs is None:
        rep.skipped["Parallel consistency (vs source)"] = "skipped: no --source-runs input supplied"
    else:
        for node, _ in iter_nodes(manifest):
            nid = node.get("id")
            ref = opts.source_runs.get(nid) if isinstance(opts.source_runs.get(nid), dict) else opts.source_runs
            for p in node.get("parallels") or []:
                if isinstance(p, dict) and p.get("name") in ref and ref[p["name"]] != p.get("print_run"):
                    rep.add("Parallel consistency",
                            f"`{nid}` / {p['name']}: print_run {p.get('print_run')} vs source {ref[p['name']]}")
    return rep


def bullets(items):
    shown = items[:LIST_CAP]
    out = [f"- {i}" for i in shown]
    rest = items[LIST_CAP:DETAIL_CAP]
    if rest:
        out.append(f"<details><summary>{len(items) - LIST_CAP} more</summary>\n")
        out += [f"- {i}" for i in rest]
        if len(items) > DETAIL_CAP:
            out.append(f"- ... and {len(items) - DETAIL_CAP} more not shown")
        out.append("\n</details>")
    return out


def render(reports):
    L = ["# Review report (advisory)", "",
         "Computed from this PR's contents; nothing here is committed. `tools/validate.py` remains the pass/fail gate.", ""]
    if not reports:
        return "\n".join(L + ["No set directories to report on."]) + "\n"
    L += ["| Check | " + " | ".join(f"`{r.dir.name}`" for r in reports) + " |",
          "|---|" + "---|" * len(reports)]
    for c in CHECKS:
        cells = []
        for r in reports:
            cells.append("skipped" if c in r.skipped else str(len(r.findings[c])))
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    L.append("")
    for r in reports:
        L += [f"## {r.dir.name}", ""]
        for p in r.problems:
            L.append(f"- Load problem: {p}")
        if r.problems:
            L.append("")
        L += ["### Structure", "", "| Node | Kind | Declared | Found | Parallels |", "|---|---|---|---|---|"]
        L += [f"| `{n[0]}` | {n[1]} | {n[2]} | {n[3]} | {n[4]} |" for n in r.nodes]
        L.append("")
        for c in CHECKS:
            if r.findings[c]:
                L += [f"**{c}** ({len(r.findings[c])})", ""] + bullets(r.findings[c]) + [""]
        for c, why in r.skipped.items():
            L.append(f"- {c}: {why}")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def changed_set_dirs(ref):
    out = subprocess.run(["git", "diff", "--name-only", f"{ref}...HEAD", "--", "data/"],
                         capture_output=True, text=True, check=True).stdout.split()
    dirs = {Path(*Path(p).parts[:3]) for p in out if len(Path(p).parts) >= 4}
    return sorted(d for d in dirs if (d / "set.yaml").exists())


def load_source_runs(path):
    text = Path(path).read_text()
    return json.loads(text) if path.endswith(".json") else yaml.safe_load(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("set_dirs", nargs="*", help="set directories (data/<genre>/<set-id>)")
    ap.add_argument("--changed-against", metavar="REF", help="report on sets touched since this git ref")
    ap.add_argument("--output", help="write markdown here instead of stdout")
    ap.add_argument("--known-names")
    ap.add_argument("--deceased")
    ap.add_argument("--marquee")
    ap.add_argument("--source-runs")
    ap.add_argument("--famous-run", type=int, default=5, help="consecutive marquee rows that count as a run")
    ap.add_argument("--check-links", action="store_true", help="HEAD-probe URLs (off by default; offline)")
    opts = ap.parse_args(argv)
    if not opts.set_dirs and not opts.changed_against:
        ap.error("give set directories or --changed-against REF")
    dirs = [Path(d) for d in opts.set_dirs]
    if opts.changed_against:
        dirs += changed_set_dirs(opts.changed_against)
    opts.known_names = read_names(opts.known_names) if opts.known_names else None
    opts.deceased = read_names(opts.deceased) if opts.deceased else None
    opts.marquee = read_names(opts.marquee) if opts.marquee else None
    opts.source_runs = load_source_runs(opts.source_runs) if opts.source_runs else None
    text = render([analyze_set(d, opts) for d in dict.fromkeys(dirs)])
    if opts.output:
        Path(opts.output).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
