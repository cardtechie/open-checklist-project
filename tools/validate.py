#!/usr/bin/env python3
"""Validate Open Checklist Project data.

Per set directory (data/<genre>/<set-id>/):
  * v0.3 (manifest form): validates set.yaml, manifest.yaml, and checklists/*.yaml
    against their schemas, then enforces the cross-file invariants from IDENTITY.md
    (unique ids/uuids, sections partition, applies_to references, etc.).
  * v0.2 (legacy exploded): validates set.yaml + cards/*.yaml against the old schemas.

Exit 0 if everything validates, 1 otherwise.
"""
import re
import sys
from pathlib import Path

import yaml
import jsonschema

SCHEMA_DIR = Path("schemas")
DATA_DIR = Path("data")


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_schema(path):
    schema = load_yaml(path)
    # Windows checkouts can read a symlink as a plain file containing its target.
    if isinstance(schema, str) and schema.endswith((".yaml", ".yml")):
        return load_yaml(Path(path).parent / schema)
    return schema


class Report:
    def __init__(self):
        self.errors = []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def schema_check(self, where, data, schema):
        v = jsonschema.Draft202012Validator(schema)
        for e in sorted(v.iter_errors(data), key=lambda e: e.path):
            loc = "/".join(str(p) for p in e.path)
            self.err(where, f"schema: {loc or '<root>'} — {e.message}")


# ---- section membership (mirrors README consume-time `applies`) ----------------

_num_re = re.compile(r"^(\D*)(\d+)$")


def _split(n):
    m = _num_re.match(str(n))
    return (m.group(1), int(m.group(2))) if m else (None, None)


def in_range(number, rng):
    pfx, val = _split(number)
    lo_p, lo_v = _split(rng["from"])
    hi_p, hi_v = _split(rng["to"])
    if None in (val, lo_v, hi_v) or not (pfx == lo_p == hi_p):
        return False
    return lo_v <= val <= hi_v


def section_of(number, sections):
    """Return the list of section ids a row number falls into (should be exactly one)."""
    hits = []
    for s in sections:
        if "numbers" in s and str(number) in [str(x) for x in s["numbers"]]:
            hits.append(s["id"])
        elif "range" in s and in_range(number, s["range"]):
            hits.append(s["id"])
    return hits


# ---- v0.3 validation -----------------------------------------------------------

def iter_nodes(manifest):
    """Yield (node, is_base) for every base set and subset, recursively."""
    def walk(node, is_base):
        yield node, is_base
        for child in node.get("subsets", []) or []:
            yield from walk(child, False)
    for b in manifest.get("base_sets", []) or []:
        yield from walk(b, True)
    for s in manifest.get("subsets", []) or []:
        yield from walk(s, False)


def validate_v03(set_dir, schemas, rep):
    where = str(set_dir)
    set_yaml = load_yaml(set_dir / "set.yaml")
    manifest = load_yaml(set_dir / "manifest.yaml")

    rep.schema_check(f"{where}/set.yaml", set_yaml, schemas["set"])
    rep.schema_check(f"{where}/manifest.yaml", manifest, schemas["manifest"])

    # set_id agreement (set.yaml <-> manifest <-> directory name)
    if set_yaml.get("set_id") != manifest.get("set_id"):
        rep.err(where, f"set_id mismatch: set.yaml={set_yaml.get('set_id')} manifest={manifest.get('set_id')}")
    if manifest.get("set_id") != set_dir.name:
        rep.err(where, f"set_id {manifest.get('set_id')} != directory {set_dir.name}")

    anchor_uuids = {}  # uuid -> "where" (product/base/subset/row), for global uniqueness
    def claim(uuid, label):
        if uuid in anchor_uuids:
            rep.err(where, f"duplicate uuid {uuid}: {label} and {anchor_uuids[uuid]}")
        else:
            anchor_uuids[uuid] = label

    claim(set_yaml.get("uuid"), "product")

    node_ids = {}
    checklist_dir = set_dir / "checklists"
    referenced_files = set()

    for node, is_base in iter_nodes(manifest):
        nid = node.get("id")
        label = f"node {nid}"
        if nid in node_ids:
            rep.err(where, f"duplicate node id: {nid}")
        node_ids[nid] = node
        claim(node.get("uuid"), label)

        # base-vs-subset type rule (schema also checks, but be explicit)
        if is_base and "type" in node:
            rep.err(where, f"base set {nid} must not have a type")
        if not is_base and not node.get("type"):
            rep.err(where, f"subset {nid} must have a non-empty type list")

        # parallel names unique within node
        pnames = [p["name"] for p in node.get("parallels", []) or []]
        dupes = {n for n in pnames if pnames.count(n) > 1}
        if dupes:
            rep.err(where, f"{nid}: duplicate parallel names {sorted(dupes)}")

        # checklist file
        cl_path = checklist_dir / f"{nid}.yaml"
        if not cl_path.exists():
            rep.err(where, f"{nid}: missing checklist file checklists/{nid}.yaml")
            continue
        referenced_files.add(cl_path.name)
        rows = load_yaml(cl_path)
        rep.schema_check(f"{where}/checklists/{nid}.yaml", rows, schemas["checklist"])
        if not isinstance(rows, list):
            continue

        numbers = [str(r.get("number")) for r in rows]
        ndupes = {n for n in numbers if numbers.count(n) > 1}
        if ndupes:
            rep.err(where, f"{nid}: duplicate card numbers within node {sorted(ndupes)[:5]}")
        for r in rows:
            claim(r.get("uuid"), f"{nid} row {r.get('number')}")

        # declared_card_count sanity
        dcc = node.get("declared_card_count")
        if dcc is not None and dcc != len(rows):
            rep.err(where, f"{nid}: declared_card_count {dcc} != {len(rows)} rows")

        # sections partition
        sections = node.get("sections")
        if sections:
            sids = [s["id"] for s in sections]
            if len(sids) != len(set(sids)):
                rep.err(where, f"{nid}: duplicate section ids")
            covered = {sid: 0 for sid in sids}
            for n in numbers:
                hits = section_of(n, sections)
                if len(hits) == 0:
                    rep.err(where, f"{nid}: card {n} is in no section (partition gap)")
                elif len(hits) > 1:
                    rep.err(where, f"{nid}: card {n} in multiple sections {hits}")
                for h in hits:
                    covered[h] += 1
            for sid, c in covered.items():
                if c == 0:
                    rep.err(where, f"{nid}: section {sid} matches no rows")

        # applies_to references
        numset = set(numbers)
        for p in node.get("parallels", []) or []:
            a = p.get("applies_to", "all")
            if isinstance(a, dict):
                for key in ("numbers", "except"):
                    for n in a.get(key, []):
                        if str(n) not in numset:
                            rep.err(where, f"{nid}: parallel {p['name']} applies_to.{key} references missing number {n}")
                for sid in a.get("sections", []):
                    if not sections or sid not in [s["id"] for s in sections]:
                        rep.err(where, f"{nid}: parallel {p['name']} applies_to.sections references undeclared section {sid}")

    # orphan checklist files (present but not referenced by any node)
    if checklist_dir.exists():
        for f in checklist_dir.glob("*.yaml"):
            if f.name not in referenced_files:
                rep.err(where, f"orphan checklist file checklists/{f.name} (no matching node id)")


# ---- v0.2 legacy validation ----------------------------------------------------

def validate_v02(set_dir, schemas, rep):
    where = str(set_dir)
    rep.schema_check(f"{where}/set.yaml", load_yaml(set_dir / "set.yaml"), schemas["v2set"])
    for card in (set_dir / "cards").glob("*.yaml"):
        rep.schema_check(str(card), load_yaml(card), schemas["v2card"])


# ---- main ----------------------------------------------------------------------

def main(argv):
    data_dir = Path(argv[1]) if len(argv) > 1 else DATA_DIR
    schema_dir = Path(argv[2]) if len(argv) > 2 else SCHEMA_DIR

    # Current-version schemas via the `schema.yaml` pointer symlinks
    # (set -> v0.3, manifest -> v0.1, checklist -> v0.1).
    schemas = {
        "set": load_schema(schema_dir / "set" / "schema.yaml"),
        "manifest": load_schema(schema_dir / "manifest" / "schema.yaml"),
        "checklist": load_schema(schema_dir / "checklist" / "schema.yaml"),
    }
    # Legacy v0.2 (exploded) schemas, loaded from their explicit version dir so the
    # `set` pointer moving to v0.3 doesn't change how legacy sets are validated.
    for legacy, fname in (("v2set", "set/v0.2/schema.yaml"), ("v2card", "card/schema.yaml")):
        p = schema_dir / fname
        if p.exists():
            schemas[legacy] = load_schema(p)

    rep = Report()
    set_dirs = sorted({p.parent for p in data_dir.rglob("set.yaml")})
    if not set_dirs:
        print(f"no sets found under {data_dir}")
        return 0

    for sd in set_dirs:
        if (sd / "manifest.yaml").exists():
            fmt = "v0.3"
            validate_v03(sd, schemas, rep)
        elif (sd / "cards").is_dir():
            fmt = "v0.2"
            validate_v02(sd, schemas, rep)
        else:
            fmt = "?"
            rep.err(str(sd), "no manifest.yaml (v0.3) or cards/ (v0.2)")
        print(f"  [{fmt}] {sd}")

    if rep.errors:
        print(f"\n❌ {len(rep.errors)} validation error(s):")
        for e in rep.errors:
            print(f"  - {e}")
        return 1
    print(f"\n✅ {len(set_dirs)} set(s) validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
