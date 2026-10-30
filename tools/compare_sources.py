#!/usr/bin/env python3
"""Decide whether two or more extracted checklist sources agree, for Discover.

Discover step 4 (docs/DISCOVER.md) used to ask the AI whether its candidate sources
agreed. This script is that decision, made by code: the AI only extracts the rows from
each source page into one file per source (schema: tools/schemas/extracted-source.yaml),
and this script compares them. The rules are documented in docs/PRODUCER.md ->
*Source comparison*.

    python tools/compare_sources.py a.yaml b.yaml
    python tools/compare_sources.py a.yaml b.yaml c.yaml --meta meta.yaml

Agreement rules (all must hold):

1. Every source's stated `card_count` is equal.
2. Each source's `cards` row count equals its own stated `card_count`.
3. The set of card numbers is equal across sources, and each number's name matches
   after whitespace-collapse and casefold.
4. Among sources with `parallels_listed: true`, the parallel ladders are equal by
   normalized name and `print_run`. Base-only sources are left out of this
   comparison; they are never counted as disagreeing.

On agreement it prints the Discover block (`<!-- ocp-discover:v1 -->` plus one fenced
yaml block) for Discover step 5 to post. `--meta <file>` adds `name`, `genre`,
`sports`, `category` and `year` to it, checked exactly as tools/check_work_order.py
checks a posted block. It never repeats `set_id` or the UUID.

On disagreement it prints {"agree": false, "sources": [...], "differences": [...]} on
stdout, `sources` being every compared url in input order: the evidence a
`source-disagreement` stop comment quotes.

It never writes to GitHub and never fetches a URL.
Exit 0 = sources agree, 10 = sources disagree, 2 = usage, read or malformed-input error
(stderr is {"error": ..., "reasons": [...]}).
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import jsonschema
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_work_order as cwo  # noqa: E402

EXIT_AGREE, EXIT_DISAGREE, EXIT_USAGE = 0, 10, 2

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "extracted-source.yaml"
META_KEYS = ("name", "genre", "sports", "category", "year")
FIELD_ORDER = ("card_count", "card_rows", "card_numbers", "card_names", "parallels")
# The largest integer a JSON consumer can hold exactly (2^53 - 1). Anything larger is
# refused on read: YAML loads a hex or binary integer of any size, and str()/repr()
# of one over 4300 digits raises, which would traceback in validation or output.
MAX_SAFE_INT = 2 ** 53 - 1
# Neither input needs more than a few levels (a source is three deep). A deeper value
# loads, but yaml.safe_dump of it can exceed the recursion limit when writing the block.
MAX_DEPTH = 16


class InputError(Exception):
    """A usage, read or malformed-input problem (exit 2)."""

    def __init__(self, error, reasons=None):
        super().__init__(error)
        self.error = error
        self.reasons = list(reasons or [])


# --------------------------------------------------------------------------- helpers

def norm(text):
    """Whitespace-collapse and casefold: the only normalization the comparator applies."""
    return " ".join(text.split()).casefold()


def _digit_run_key(run):
    """Order a decimal digit run by numeric value without int().

    CPython refuses int() on a run longer than 4300 digits, and a card number is a
    free string, so the run is compared as (length, digits) once it is mapped to
    ASCII and stripped of leading zeros. That is the same order int() gives.
    """
    digits = "".join(str(unicodedata.decimal(c)) for c in run).lstrip("0")
    return (len(digits), digits)


def natural_key(number):
    """Sort card numbers as strings, with digit runs compared numerically (2 < 10)."""
    # isdecimal, not isdigit: re's \d matches exactly the Unicode decimal digits,
    # while isdigit also admits superscripts such as "\u00b2" that have no
    # decimal value.
    return [(0, _digit_run_key(part), "") if part.isdecimal() else (1, (0, ""), part)
            for part in re.split(r"(\d+)", number) if part != ""]


def load_schema():
    try:
        return yaml.safe_load(SCHEMA_PATH.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise InputError(f"cannot read schema {SCHEMA_PATH}: {e}") from e


def _read_yaml(path):
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, UnicodeDecodeError) as e:
        raise InputError(f"cannot read {path}: {e}") from e
    except yaml.YAMLError as e:
        first = str(e).splitlines()[0] if str(e) else "parse error"
        raise InputError(f"{path}: yaml is malformed: {first}") from e
    except (ValueError, TypeError, OverflowError, RecursionError) as e:
        # Raised by the loader itself, not as a YAMLError: an integer over CPython's
        # 4300-digit limit, an impossible date such as 2025-02-30, or nesting deeper
        # than the recursion limit.
        first = str(e).splitlines()[0] if str(e) else type(e).__name__
        raise InputError(f"{path}: yaml is malformed: {first}") from e
    problems = _value_problems(data)
    if problems:
        raise InputError(f"{path}: value out of range", problems)
    return data


def _value_problems(data):
    """Reasons a loaded YAML value cannot be processed safely: integers whose magnitude
    exceeds MAX_SAFE_INT, and nesting deeper than MAX_DEPTH. Iterative, so a deep value
    cannot exhaust the recursion limit here either."""
    problems, too_deep = [], False
    stack = [(data, (), 0)]
    while stack:
        value, path, depth = stack.pop()
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            if abs(value) > MAX_SAFE_INT:
                problems.append(f"{'/'.join(str(p) for p in path) or '<root>'}: larger than {MAX_SAFE_INT}")
            continue
        if isinstance(value, (dict, list)):
            if depth >= MAX_DEPTH:
                too_deep = True
                continue
            items = value.items() if isinstance(value, dict) else enumerate(value)
            stack.extend((v, path + (k,), depth + 1) for k, v in reversed(list(items)))
    if too_deep:
        problems.append(f"nested deeper than {MAX_DEPTH} levels")
    return problems


def load_source(path, validator):
    """Load and validate one extracted-source file, or raise InputError."""
    data = _read_yaml(path)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        raise InputError(f"{path}: does not match {SCHEMA_PATH.name}",
                         [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
                          for e in errors])
    reasons = []
    problem = cwo.source_url_problem(data["url"])
    if problem:
        reasons.append(f"url {problem}")
    seen = set()
    for card in data["cards"]:
        if card["number"] in seen:
            reasons.append(f"duplicate card number {card['number']!r}")
        seen.add(card["number"])
    rungs = set()
    for p in data["parallels"]:
        key = (norm(p["name"]), p["print_run"])
        if key in rungs:
            reasons.append(f"duplicate parallel {p['name']!r} with print_run {p['print_run']}")
        rungs.add(key)
    if reasons:
        raise InputError(f"{path}: malformed extraction", reasons)
    return data


def load_meta(path):
    """Load the optional --meta file and check it as check_work_order checks a block."""
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise InputError(f"{path}: meta must be a mapping")
    unknown = sorted(str(k) for k in data if k not in META_KEYS)
    if unknown:
        raise InputError(f"{path}: meta has unknown keys", [f"unknown key {k!r}; allowed: {list(META_KEYS)}"
                                                             for k in unknown])
    return data


# --------------------------------------------------------------------------- compare

def compare(sources):
    """Return the ordered list of differences between validated sources ([] = agree)."""
    urls = [s["url"] for s in sources]
    found = {f: [] for f in FIELD_ORDER}

    # 1. Stated card counts.
    counts = {s["url"]: s["card_count"] for s in sources}
    if len(set(counts.values())) > 1:
        found["card_count"].append({"field": "card_count", "values": counts})

    # 2. A source whose rows do not match its own stated count is self-inconsistent.
    bad_rows = {s["url"]: {"stated": s["card_count"], "rows": len(s["cards"])}
                for s in sources if len(s["cards"]) != s["card_count"]}
    if bad_rows:
        found["card_rows"].append({"field": "card_rows", "values": bad_rows})

    # 3. Card numbers, then names for numbers more than one source lists.
    names = {s["url"]: {c["number"]: c["name"] for c in s["cards"]} for s in sources}
    # Raw number breaks ties: "1", "01" and "001" share a natural key, and set
    # iteration order would otherwise make the output vary between processes.
    all_numbers = sorted({n for by_num in names.values() for n in by_num},
                         key=lambda n: (natural_key(n), n))
    for number in all_numbers:
        listed = {u: number in names[u] for u in urls}
        if not all(listed.values()):
            found["card_numbers"].append({"field": "card_numbers", "number": number, "values": listed})
        having = {u: names[u][number] for u in urls if number in names[u]}
        if len(having) > 1 and len({norm(v) for v in having.values()}) > 1:
            found["card_names"].append({"field": "card_names", "number": number, "values": having})

    # 4. Parallel ladders, among the sources that list one.
    ladder_sources = [s for s in sources if s["parallels_listed"]]
    if len(ladder_sources) > 1:
        ladders = {s["url"]: {(norm(p["name"]), p["print_run"]): p["name"] for p in s["parallels"]}
                   for s in ladder_sources}
        rungs = {}
        for s in ladder_sources:  # first spelling seen, in input order, names the rung
            for key, name in ladders[s["url"]].items():
                rungs.setdefault(key, name)
        for key in sorted(rungs, key=lambda k: (k[0], -1 if k[1] is None else k[1])):
            listed = {s["url"]: key in ladders[s["url"]] for s in ladder_sources}
            if not all(listed.values()):
                found["parallels"].append({"field": "parallels", "name": rungs[key],
                                           "print_run": key[1], "values": listed})

    return [d for f in FIELD_ORDER for d in found[f]]


def discover_block(sources, meta=None):
    """The Discover block text for agreeing sources, validated by check_work_order."""
    data = {}
    for key in META_KEYS:
        if meta and key in meta:
            data[key] = meta[key]
    data["sources"] = [{"url": s["url"], "card_count": s["card_count"],
                        "parallels_listed": s["parallels_listed"]} for s in sources]
    body = f"{cwo.DISCOVER_MARKER}\n```yaml\n{yaml.safe_dump(data, sort_keys=False, allow_unicode=True)}```\n"
    reasons = []
    parsed = cwo.parse_discover(body, reasons)
    if reasons:
        raise InputError("the Discover block would not pass tools/check_work_order.py", reasons)
    # The block must say exactly what --meta said. YAML can rewrite a value on the way
    # through: a NEL (U+0085) inside a plain string is folded to a space, for one.
    changed = [f"meta {key} reads back as {parsed.get(key)!r}, not {data[key]!r}"
               for key in META_KEYS if key in data and parsed.get(key) != data[key]]
    if changed:
        raise InputError("a --meta value does not survive the Discover block unchanged", changed)
    return body


# --------------------------------------------------------------------------- main

def _fail(err):
    print(json.dumps({"error": err.error, "reasons": err.reasons}, indent=2), file=sys.stderr)
    return EXIT_USAGE


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser whose errors are InputErrors, so they reach _fail as JSON.

    argparse's default error() prints its own usage text and exits 2 before _fail
    can run, which breaks the documented exit-2 contract of a JSON stderr.
    """

    def error(self, message):
        raise InputError("invalid command line", [message])


def main(argv=None):
    ap = _Parser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sources", nargs="*", help="two or more extracted-source files")
    ap.add_argument("--meta", help="yaml file with name/genre/sports/category/year for the block")
    try:
        try:
            args = ap.parse_args(argv)
        except SystemExit as e:  # --help: argparse prints it and exits 0
            return EXIT_USAGE if e.code else 0
        if len(args.sources) < 2:
            raise InputError("give two or more extracted-source files",
                             [f"got {len(args.sources)}; a single source skips the comparator"])
        validator = jsonschema.Draft202012Validator(load_schema())
        sources = [load_source(p, validator) for p in args.sources]
        seen = {}
        for path, s in zip(args.sources, sources):
            # Same normalization the URL policy validates, so padding cannot hide a duplicate.
            url = s["url"].strip()
            if url in seen:
                raise InputError("duplicate source url",
                                 [f"{path} and {seen[url]} both have url {url}"])
            seen[url] = path
        meta = load_meta(args.meta) if args.meta else None
        # Built before comparing so a bad --meta is exit 2 whatever the sources say.
        block = discover_block(sources, meta)
        differences = compare(sources)
        if differences:
            # `sources` is every compared url in input order. A difference's `values`
            # can be sparse (card_rows lists only self-inconsistent sources, parallels
            # only ladder sources), so it alone cannot say which sources were compared.
            print(json.dumps({"agree": False, "sources": [s["url"] for s in sources],
                              "differences": differences}, indent=2))
            return EXIT_DISAGREE
        print(block, end="")
        return EXIT_AGREE
    except InputError as e:
        return _fail(e)


if __name__ == "__main__":
    sys.exit(main())
