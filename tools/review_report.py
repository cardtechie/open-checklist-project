#!/usr/bin/env python3
"""Computed review report for Open Checklist Project sets.

Derives a one-page markdown report from a set's set.yaml, manifest.yaml and
checklists/*.yaml so a human reviewer can judge a conversion without reading ~70 YAML
files. The report is ADVISORY and computed on demand: nothing it emits is committed, and
`tools/validate.py` remains the pass/fail gate for schema and IDENTITY.md invariants.

Exit code is 0 whenever a report was produced (findings never fail the run); non-zero
only for bad arguments or a crash. The one exception is `--require-subsets`, which exits 3
when a set misses a Discover-listed subset (see below).

Usage:
    python tools/review_report.py data/baseball/2026-bowman [more set dirs ...]
    python tools/review_report.py --changed-against origin/main

Optional input files enable checks that need data this repository does not hold. Without
one, that check prints an explicit "skipped" line instead of silently passing:
    --known-names FILE   one player name per line (e.g. an index exported from tcapi)
    --deceased FILE      one name per line; an optional ",date" suffix is ignored
    --marquee FILE       one famous-player name per line
    --source-runs FILE   YAML/JSON {parallel: print_run} or {node-id: {parallel: print_run}}
    --discover FILE      the tools/check_work_order.py verdict (JSON/YAML) or any mapping
                         with a `subsets` list; enables the "Subset completeness" check

A set is done only when every subset Discover listed is authored at its stated count,
with a ladder where the source lists one. `--require-subsets` makes that check a gate for
the producer: it exits 3 when the check has a finding, and 2 when no usable `subsets`
list was supplied, so a missing input can never read as a pass.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import find_dupes, _split  # noqa: E402

LIST_CAP = 10          # items shown inline before the rest fold into <details>
DETAIL_CAP = 200       # hard cap on items listed at all
LINK_CAP = 25          # max distinct URLs probed with --check-links
NODE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # manifest schema slug pattern
URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+")
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "localhost", "127.0.0.1",
    "via.placeholder.com", "placehold.co", "placeholder.com", "picsum.photos",
    "lorempixel.com", "dummyimage.com", "fakeimg.pl",
)
PLACEHOLDER_WORDS = ("placeholder", "your-", "todo", "tbd", "xxx", "/null", "/undefined", "/none")

CHECKS = [
    "Declared vs actual count", "Parallel consistency", "Parallel consistency (vs source)",
    "Numbering gaps", "Subset completeness",
    "Duplicate card numbers", "Duplicate subjects", "Placeholder / dead URLs",
    "Never-seen names", "Deceased with live autograph", "Sequential famous player",
]


def load_yaml(path):
    """Load YAML defensively. Returns (data, error-string-or-None)."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except UnicodeDecodeError as e:
        return None, f"cannot decode {path} as UTF-8: {e.reason} at byte {e.start}"
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


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|~!])")


def md_text(value):
    """Make an untrusted value inert in Markdown prose: flatten line breaks and
    backslash-escape the characters that start formatting, links, headings or HTML."""
    return _MD_SPECIAL.sub(r"\\\1", " ".join(str(value).splitlines()))


def md_cell(value):
    """Make a value safe for one Markdown table cell. Same as md_text: pipes are escaped
    (so the cell delimiter survives), line breaks flattened, and links, images, emphasis
    and HTML rendered as inert text."""
    return md_text(value)


def as_list(value):
    """A YAML list field, or [] when it is absent or not a list."""
    return value if isinstance(value, list) else []


def node_types(node, problems, nid):
    """A node's `type` as a list of strings; a malformed value is recorded, not raised."""
    t = node.get("type")
    if t is None:
        return []
    if not isinstance(t, list):
        problems.append(f"node {nid}: type is {type(t).__name__}, not a list")
        return [str(t)]
    return [str(x) for x in t]


def iter_nodes_safe(manifest, problems):
    """Like validate.iter_nodes, but records malformed containers as load problems
    instead of raising, so the advisory report still covers what can be read.
    Problems are plain text; render() escapes them for Markdown."""
    def children(container, where):
        if container is None:
            return []
        if not isinstance(container, list):
            problems.append(f"{where} is {type(container).__name__}, not a list; skipped")
            return []
        return container

    def walk(node, is_base, where, ancestors):
        if not isinstance(node, dict):
            problems.append(f"{where} is {type(node).__name__}, not a mapping; skipped")
            return
        if id(node) in ancestors:  # a YAML alias back to a containing node
            problems.append(f"{where} refers back to a containing node (cyclic YAML); skipped")
            return
        yield node, is_base
        nid = node.get("id")
        ancestors = ancestors | {id(node)}
        for child in children(node.get("subsets"), f"subsets of node {nid}"):
            yield from walk(child, False, f"a subset of node {nid}", ancestors)

    for b in children(manifest.get("base_sets"), "base_sets"):
        yield from walk(b, True, "a base_sets entry", frozenset())
    for sub in children(manifest.get("subsets"), "subsets"):
        yield from walk(sub, False, "a subsets entry", frozenset())


def norm(name):
    return " ".join(str(name).lower().split())


def walk_strings(obj, _seen=None):
    """Every string in a YAML document. Each container is visited once, so a cyclic
    alias (or a heavily shared one) cannot recurse forever or blow up the walk."""
    seen = set() if _seen is None else _seen
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, (dict, list)):
        if id(obj) in seen:
            return
        seen.add(id(obj))
        for v in (obj.values() if isinstance(obj, dict) else obj):
            yield from walk_strings(v, seen)


def is_placeholder_url(url):
    low = url.lower()
    host = re.sub(r"^https?://", "", low).split("/", 1)[0].split(":", 1)[0]
    if any(host == h or host.endswith("." + h) for h in PLACEHOLDER_HOSTS):
        return True
    return any(w in low for w in PLACEHOLDER_WORDS)


def _request(url, method):
    headers = {"User-Agent": "ocp-review-report"}
    if method == "GET":
        headers["Range"] = "bytes=0-0"  # bounded: we only need the status line
    req = urllib.request.Request(url, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def probe(url):
    """Probe a URL. Returns None if it responds OK, ("restricted", detail) for an
    access-controlled response (401/403 do not establish a dead link),
    ("inconclusive", detail) when the probe itself failed (429, 5xx, DNS/TLS error,
    timeout) and says nothing about the link, or ("dead", detail) for a confirmed
    failure (any other 4xx). A server that rejects HEAD (405/501) is retried with a
    bounded GET before being judged."""
    for method in ("HEAD", "GET"):
        try:
            status = _request(url, method)
            return None if status < 400 else ("dead", f"HTTP {status}")
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (405, 501):
                continue
            if e.code in (401, 403):
                return ("restricted", f"HTTP {e.code}")
            if e.code == 429 or e.code >= 500:
                return ("inconclusive", f"HTTP {e.code}")
            return ("dead", f"HTTP {e.code}")
        except Exception as e:  # noqa: BLE001 - network/DNS/TLS/timeout: not proof of a dead link
            return ("inconclusive", type(e).__name__)
    return ("inconclusive", "no response")


def row_players(row):
    out = []
    for s in as_list(row.get("subjects")):
        if not isinstance(s, dict):
            continue
        for e in as_list(s.get("entities")):
            if isinstance(e, dict) and e.get("role") == "player" and e.get("name"):
                out.append(str(e["name"]))
    return out


def subject_key(row):
    subs = []
    for s in as_list(row.get("subjects")):
        if isinstance(s, dict):
            ents = tuple(sorted((str(e.get("role")), norm(e.get("name")))
                                for e in as_list(s.get("entities"))
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
        self.partial = {}                                   # check -> why it only partly ran
        self.nodes = []                                     # per-node table rows
        self.parallels = []                                 # every parallel declaration

    def add(self, check, text):
        self.findings[check].append(text)


def check_subsets(rep, listed, authored):
    """Compare the Discover-listed subsets with the authored non-base nodes.

    A listed subset is satisfied by a node with the same normalized name whose `type`
    includes the listed type and whose row count equals the stated card_count. When
    Discover says the source lists the subset's ladder, the node must carry parallels.
    Nothing is judged beyond that; counts are the source's, never recomputed here.
    """
    for sub in listed:
        name, kind, count = sub["name"], sub["type"], sub["card_count"]
        label = f"`{md_text(name)}` ({md_text(kind)})"
        match = [a for a in authored if a[1] == norm(name) and kind in a[2]]
        if not match:
            rep.add("Subset completeness", f"{label}: Discover lists {count} cards, no such subset is authored")
            continue
        nid, _, _, rows, ladder = match[0]
        if rows != count:
            rep.add("Subset completeness", f"{label}: Discover lists {count} cards, `{md_text(nid)}` has {rows}")
        if sub.get("parallels_listed") is True and ladder == 0:
            rep.add("Subset completeness", f"{label}: the source lists a parallel ladder, `{md_text(nid)}` has none")


def load_discover_subsets(path):
    """Load --discover; returns (subsets-list, error-string-or-None)."""
    try:
        data = yaml.safe_load(Path(path).read_text())  # JSON is YAML
    except (OSError, ValueError, yaml.YAMLError) as e:
        return None, f"cannot load {path}: {str(e).splitlines()[0] if str(e) else type(e).__name__}"
    subs = data.get("subsets") if isinstance(data, dict) else None
    if not isinstance(subs, list):
        return None, f"{path} must be a mapping with a `subsets` list (a check_work_order.py verdict has one)"
    bad = [i for i, x in enumerate(subs, 1)
           if not (isinstance(x, dict) and isinstance(x.get("name"), str) and x["name"].strip()
                   and isinstance(x.get("type"), str) and is_count(x.get("card_count")))]
    if bad:
        return None, f"{path}: subset(s) {bad} need a name, a type and a positive integer card_count"
    return subs, None


def is_count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def analyze_set(set_dir, opts):
    rep = SetReport(set_dir)
    set_root = rep.dir.resolve()

    def inside_set(path):
        """True when `path` resolves inside this set directory; a symlink out of the set
        (to a file or to the checklists/ root) must not feed data into the report."""
        return path.resolve().is_relative_to(set_root)

    def load_in_set(path):
        if not inside_set(path):
            return None, f"{path} resolves outside the set directory; skipped"
        return load_yaml(path)

    set_yaml, err = load_in_set(rep.dir / "set.yaml")
    if err:
        rep.problems.append(err)
    manifest, err = load_in_set(rep.dir / "manifest.yaml")
    if err:
        rep.problems.append(err)
    if not isinstance(manifest, dict):
        rep.problems.append("manifest.yaml is not a mapping; structural checks skipped")
        manifest = {}
    all_docs = [d for d in (set_yaml, manifest) if d is not None]

    seen_names = set()
    nodes_rows = {}
    checklists = (rep.dir / "checklists").resolve()
    # The containment test below is only meaningful if the checklists/ root itself stays
    # inside the set: a symlinked root would move both sides of it into the link target.
    if not checklists.is_relative_to(set_root) or checklists == set_root:
        rep.problems.append("checklists/ resolves outside the set directory; node files skipped")
        manifest = {}
    unmatched_src = []  # parallel declarations --source-runs had no entry for
    authored_subsets = []  # (id, norm(name), types, rows, parallel count) of every non-base node
    for node, is_base in iter_nodes_safe(manifest, rep.problems):
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            rep.problems.append("a node has no usable id; skipped")
            continue
        # The id becomes a path component, so it must be a manifest slug and must not
        # resolve outside this set's checklists/ directory (e.g. via a symlink).
        path = rep.dir / "checklists" / f"{nid}.yaml"
        if not NODE_ID_RE.match(nid) or not path.resolve().is_relative_to(checklists):
            rep.problems.append(f"node id {nid!r} is not a valid slug inside checklists/; skipped")
            continue
        types = node_types(node, rep.problems, nid)
        rows, err = load_yaml(path)
        if err:
            rep.problems.append(err)
            rows = []
        if not isinstance(rows, list):
            rows = []
        rows = [r for r in rows if isinstance(r, dict)]
        all_docs.append(rows)
        nodes_rows[nid] = rows
        numbers = [str(r["number"]) for r in rows if r.get("number") is not None]
        parallels = [p for p in as_list(node.get("parallels")) if isinstance(p, dict)]
        for r in rows:
            seen_names.update(norm(n) for n in row_players(r))

        if not is_base:
            authored_subsets.append((nid, norm(node.get("name") or nid), types, len(rows), len(parallels)))

        # Structure: declared vs actual (shown, not re-gated; validate.py owns the error)
        dcc = node.get("declared_card_count")
        mark = ""
        if isinstance(dcc, int) and dcc != len(rows):
            mark = " (mismatch)"
            rep.add("Declared vs actual count", f"`{nid}`: declared {dcc}, found {len(rows)}")
        rep.nodes.append((nid, "base" if is_base else ",".join(types) or "subset",
                          "-" if dcc is None else str(dcc), str(len(rows)) + mark, str(len(parallels))))

        # Parallels: list every declaration, then check local consistency
        src = None
        if opts.source_runs is not None:
            src = opts.source_runs.get(nid) if isinstance(opts.source_runs.get(nid), dict) else opts.source_runs
        for p in parallels:
            name, run, ser = p.get("name", "<unnamed>"), p.get("print_run"), p.get("serial_numbered")
            src_run = src.get(name) if isinstance(src, dict) and isinstance(name, str) else None
            if isinstance(src_run, dict):  # another node's map in a per-node file, not a run
                src_run = None
            rep.parallels.append((nid, name, run, ser, src_run))
            if opts.source_runs is not None and src_run is None:
                unmatched_src.append(f"{nid} / {name}")
            if src_run is not None and src_run != run:
                rep.add("Parallel consistency (vs source)",
                        f"`{nid}` / {md_text(name)}: print_run {md_text(run)} vs source {md_text(src_run)}")
            if ser and run is None:
                rep.add("Parallel consistency", f"`{nid}` / {md_text(name)}: serial_numbered without print_run")
            if run is not None and not ser:
                rep.add("Parallel consistency", f"`{nid}` / {md_text(name)}: print_run {md_text(run)} but not serial_numbered")
            if run == 0:
                rep.add("Parallel consistency", f"`{nid}` / {md_text(name)}: print_run is 0")

        # Variation nodes are sparse by nature (a subset of the base numbers), so a gap
        # there is expected, not a finding.
        is_variation = "variation" in [t.lower() for t in types]
        gaps = [] if is_variation else gap_ranges(numbers)
        if gaps:
            rep.add("Numbering gaps", f"`{nid}`: missing {md_text(', '.join(gaps[:8]))}" + (" ..." if len(gaps) > 8 else ""))
        dn = find_dupes(numbers)
        if dn:
            rep.add("Duplicate card numbers", f"`{nid}`: {md_text(', '.join(sorted(dn)[:10]))}")

        by_key = defaultdict(list)
        for r in rows:
            k = subject_key(r)
            if k is not None:
                by_key[k].append(str(r.get("number")))
        for k, nums in by_key.items():
            if len(nums) > 1:
                who = "; ".join(" + ".join(n for _, n in s) for s in k)
                rep.add("Duplicate subjects", f"`{nid}`: {md_text(who)} on {md_text(', '.join(nums[:6]))}")

        # Sequential famous player / deceased autograph (input-file driven). A run only
        # extends across card numbers that are consecutive within the same prefix, so a
        # numbering gap or out-of-order row breaks it rather than counting as adjacent.
        if opts.marquee is not None:
            run_ = []
            def flush():
                if len(run_) >= opts.famous_run:
                    rep.add("Sequential famous player",
                            f"`{nid}`: {len(run_)} consecutive marquee cards "
                            f"{md_text(run_[0][0])}..{md_text(run_[-1][0])}")
            for r in rows:
                ps = row_players(r)
                pfx, val = _split(r.get("number"))
                if not (ps and val is not None and all(norm(p) in opts.marquee for p in ps)):
                    flush()
                    run_ = []
                    continue
                if run_ and not (run_[-1][1] == pfx and run_[-1][2] + 1 == val):
                    flush()
                    run_ = []
                run_.append((r.get("number"), pfx, val))
            flush()
        if opts.deceased is not None and any("autograph" in t.lower() for t in types):
            for r in rows:
                hit = [p for p in row_players(r) if norm(p) in opts.deceased]
                if hit:
                    rep.add("Deceased with live autograph",
                            f"`{nid}` {md_text(r.get('number'))}: {md_text(', '.join(hit))}")

    # Placeholder / dead URLs: every string in all three file kinds
    urls = {}
    for doc in all_docs:
        for s in walk_strings(doc):
            for u in URL_RE.findall(s):
                urls[u.rstrip(".,;")] = True
    for u in urls:
        if is_placeholder_url(u):
            rep.add("Placeholder / dead URLs", f"placeholder-looking URL: {md_text(u)}")
    if opts.check_links:
        for u in list(urls)[:LINK_CAP]:
            if not is_placeholder_url(u):
                bad = probe(u)
                if bad and bad[0] == "restricted":
                    rep.add("Placeholder / dead URLs",
                            f"access-restricted ({bad[1]}), not confirmed dead: {md_text(u)}")
                elif bad and bad[0] == "inconclusive":
                    rep.add("Placeholder / dead URLs",
                            f"probe inconclusive ({md_text(bad[1])}), not confirmed dead: {md_text(u)}")
                elif bad:
                    rep.add("Placeholder / dead URLs", f"dead link ({bad[1]}): {md_text(u)}")
        if len(urls) > LINK_CAP:
            rep.add("Placeholder / dead URLs", f"link probe capped at {LINK_CAP} of {len(urls)} URLs")
    else:
        # Without the probe only placeholder-looking strings were scanned, so a 0 here says
        # nothing about dead links; flag the row as partial rather than as a clean pass.
        rep.partial["Placeholder / dead URLs"] = ("partial: dead-link probe not run (no --check-links); "
                                                  "only placeholder-looking URLs were checked")

    # Never-seen names
    if opts.known_names is None:
        rep.skipped["Never-seen names"] = "skipped: no --known-names input supplied"
    else:
        unseen = sorted({n for rows in nodes_rows.values() for r in rows for n in row_players(r)
                         if norm(n) not in opts.known_names})
        for n in unseen:
            rep.add("Never-seen names", md_text(n))
    if opts.discover is None:
        rep.skipped["Subset completeness"] = "skipped: no --discover input supplied"
    else:
        check_subsets(rep, opts.discover, authored_subsets)
    if opts.deceased is None:
        rep.skipped["Deceased with live autograph"] = "skipped: no --deceased input supplied"
    if opts.marquee is None:
        rep.skipped["Sequential famous player"] = "skipped: no --marquee input supplied"

    # Source-declared print runs are compared per parallel above; without the input the
    # comparison never ran, so it reports as skipped rather than as zero mismatches.
    if opts.source_runs is None:
        rep.skipped["Parallel consistency (vs source)"] = "skipped: no --source-runs input supplied"
    elif unmatched_src:
        # A declaration with no source entry was never compared, so a clean count would
        # overstate coverage; name what was missed instead.
        shown = ", ".join(unmatched_src[:LIST_CAP]) + (" ..." if len(unmatched_src) > LIST_CAP else "")
        rep.partial["Parallel consistency (vs source)"] = (
            f"partial: {len(unmatched_src)} declaration(s) had no --source-runs entry and were "
            f"not compared: {md_text(shown)}")
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
    L += ["| Check | " + " | ".join(md_cell(r.dir.name) for r in reports) + " |",
          "|---|" + "---|" * len(reports)]
    for c in CHECKS:
        cells = []
        for r in reports:
            if c in r.skipped:
                cells.append("skipped")
            elif c in r.partial:
                cells.append(f"{len(r.findings[c])} (partial)")
            else:
                cells.append(str(len(r.findings[c])))
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    L.append("")
    for r in reports:
        L += [f"## {md_text(r.dir.name)}", ""]
        for p in r.problems:
            L.append(f"- Load problem: {md_text(p)}")
        if r.problems:
            L.append("")
        L += ["### Structure", "", "| Node | Kind | Declared | Found | Parallels |", "|---|---|---|---|---|"]
        L += ["| " + " | ".join(md_cell(v) for v in n) + " |" for n in r.nodes]
        L.append("")
        if r.parallels:
            L += ["### Parallels", "", f"<details><summary>{len(r.parallels)} parallel declarations</summary>", "",
                  "| Node | Parallel | Print run | Serial numbered | Source run |", "|---|---|---|---|---|"]
            cell = lambda v: "-" if v is None else str(v)  # noqa: E731
            L += [f"| `{md_cell(nid)}` | {md_cell(name)} | {md_cell(cell(run))} | {'yes' if ser else 'no'} "
                  f"| {md_cell(cell(src))} |"
                  for nid, name, run, ser, src in r.parallels[:DETAIL_CAP]]
            if len(r.parallels) > DETAIL_CAP:
                L.append(f"\n_... and {len(r.parallels) - DETAIL_CAP} more parallels not shown._")
            L += ["", "</details>", ""]
        for c in CHECKS:
            if r.findings[c]:
                L += [f"**{c}** ({len(r.findings[c])})", ""] + bullets(r.findings[c]) + [""]
        for c, why in list(r.skipped.items()) + list(r.partial.items()):
            L.append(f"- {c}: {why}")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def changed_set_dirs(ref):
    out = subprocess.run(["git", "diff", "--name-only", f"{ref}...HEAD", "--", "data/"],
                         capture_output=True, text=True, check=True).stdout.split()
    dirs = {Path(*Path(p).parts[:3]) for p in out if len(Path(p).parts) >= 4}
    return sorted(d for d in dirs if (d / "set.yaml").exists())


def load_source_runs(path):
    """Load --source-runs; returns (mapping, error-string-or-None). Only a mapping is usable."""
    try:
        text = Path(path).read_text()
        data = json.loads(text) if path.endswith(".json") else yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError) as e:
        return None, f"cannot load {path}: {str(e).splitlines()[0] if str(e) else type(e).__name__}"
    if not isinstance(data, dict):
        return None, (f"{path} must be a mapping ({{parallel: print_run}} or {{node-id: {{parallel: print_run}}}}), "
                      f"got {type(data).__name__}")
    return data, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("set_dirs", nargs="*", help="set directories (data/<genre>/<set-id>)")
    ap.add_argument("--changed-against", metavar="REF", help="report on sets touched since this git ref")
    ap.add_argument("--output", help="write markdown here instead of stdout")
    ap.add_argument("--known-names")
    ap.add_argument("--deceased")
    ap.add_argument("--marquee")
    ap.add_argument("--source-runs")
    ap.add_argument("--discover", help="check_work_order.py verdict (or a mapping with `subsets`)")
    ap.add_argument("--require-subsets", action="store_true",
                    help="exit 3 when a set misses a Discover-listed subset (needs --discover)")
    ap.add_argument("--famous-run", type=int, default=5, help="consecutive marquee rows that count as a run")
    ap.add_argument("--check-links", action="store_true", help="HEAD-probe URLs (off by default; offline)")
    opts = ap.parse_args(argv)
    if not opts.set_dirs and not opts.changed_against:
        ap.error("give set directories or --changed-against REF")
    if opts.famous_run < 1:
        ap.error(f"--famous-run must be at least 1, got {opts.famous_run}")
    dirs = [Path(d) for d in opts.set_dirs]
    if opts.changed_against:
        dirs += changed_set_dirs(opts.changed_against)
    opts.known_names = read_names(opts.known_names) if opts.known_names else None
    opts.deceased = read_names(opts.deceased) if opts.deceased else None
    opts.marquee = read_names(opts.marquee) if opts.marquee else None
    if opts.source_runs:
        opts.source_runs, err = load_source_runs(opts.source_runs)
        if err:
            ap.error(f"--source-runs: {err}")
    else:
        opts.source_runs = None
    if opts.discover:
        opts.discover, err = load_discover_subsets(opts.discover)
        if err:
            ap.error(f"--discover: {err}")
    else:
        opts.discover = None
    if opts.require_subsets and opts.discover is None:
        ap.error("--require-subsets needs --discover")
    reports = [analyze_set(d, opts) for d in dict.fromkeys(dirs)]
    text = render(reports)
    if opts.output:
        Path(opts.output).write_text(text)
    else:
        sys.stdout.write(text)
    if opts.require_subsets and any(r.findings["Subset completeness"] for r in reports):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
