#!/usr/bin/env python3
"""Validate Open Checklist Project data.

Per set directory (data/<genre>/<set-id>/):
  * v0.3 (manifest form): validates set.yaml, manifest.yaml, and checklists/*.yaml
    against their schemas, then enforces the cross-file invariants from IDENTITY.md
    (unique ids/uuids, sections partition, applies_to references, etc.).
  * v0.2 (legacy exploded): validates set.yaml + cards/*.yaml against the old schemas.

This is a CI gate, so it is defensive: malformed YAML, unreadable files, and
schema-invalid shapes are recorded as errors and reported at the end rather than
crashing the run. Exit 0 if everything validates, 1 otherwise.
"""
import re
import sys
from pathlib import Path

import yaml
import jsonschema

SCHEMA_DIR = Path("schemas")
DATA_DIR = Path("data")

# Enforce format constraints (uuid / date / uri) in addition to structure. Formats
# whose optional backing library isn't installed are silently skipped by jsonschema.
FORMAT_CHECKER = jsonschema.FormatChecker()


def load_schema(path):
    """Load a schema file (following the pointer-symlink-as-text fallback). Schema
    files are part of the repo, not user data, so a bad schema is a setup error and
    is allowed to raise."""
    with open(path) as f:
        schema = yaml.safe_load(f)
    # Windows checkouts can read a symlink as a plain file containing its target.
    if isinstance(schema, str) and schema.endswith((".yaml", ".yml")):
        with open(Path(path).parent / schema) as f:
            schema = yaml.safe_load(f)
    return schema


def _path_key(err):
    """A sortable key for a jsonschema error path (a deque of mixed str/int)."""
    return [str(p) for p in err.path]


class Report:
    def __init__(self):
        self.errors = []
        self.anchor_uuids = {}  # uuid -> label, unique across the WHOLE run (IDENTITY.md #3)

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def claim_uuid(self, where, uuid, label):
        """Record a committed anchor uuid, reporting a duplicate against any set seen
        so far in this run (uniqueness is global, not per-set). Missing/non-string
        uuids are reported by schema validation, so they're skipped here."""
        if not isinstance(uuid, str) or not uuid:
            return
        if uuid in self.anchor_uuids:
            self.err(where, f"duplicate uuid {uuid}: {label} and {self.anchor_uuids[uuid]}")
        else:
            self.anchor_uuids[uuid] = label

    def load_yaml(self, path, where):
        """Load YAML, recording parse/read errors instead of raising. Returns the
        parsed data, or None on failure (or on an empty/null document)."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            self.err(where, f"file not found: {path}")
            return None
        except yaml.YAMLError as e:
            self.err(where, f"invalid YAML: {str(e).splitlines()[0] if str(e) else e}")
            return None
        except OSError as e:
            self.err(where, f"cannot read file: {e}")
            return None
        if data is None:
            self.err(where, "empty or null document")
        return data

    def schema_check(self, where, data, schema):
        # None means the file failed to load or was empty — already reported by
        # load_yaml; skip so we don't pile on a noisy "None is not of type ..." error.
        if data is None:
            return
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
            errors = sorted(validator.iter_errors(data), key=_path_key)
        except Exception as e:  # pragma: no cover - defensive
            self.err(where, f"could not run schema validation: {e}")
            return
        for e in errors:
            loc = "/".join(str(p) for p in e.path)
            self.err(where, f"schema: {loc or '<root>'} — {e.message}")


# ---- section membership (mirrors README consume-time `applies`) ----------------

_num_re = re.compile(r"^(\D*)(\d+)$")


def _split(n):
    m = _num_re.match(str(n))
    return (m.group(1), int(m.group(2))) if m else (None, None)


def in_range(number, rng):
    if not isinstance(rng, dict):
        return False
    pfx, val = _split(number)
    lo_p, lo_v = _split(rng.get("from"))
    hi_p, hi_v = _split(rng.get("to"))
    if None in (val, lo_v, hi_v) or not (pfx == lo_p == hi_p):
        return False
    return lo_v <= val <= hi_v


def section_of(number, sections):
    """Return the list of section ids a row number falls into (should be exactly one).
    Tolerates malformed section entries (schema validation reports those separately)."""
    hits = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        if "numbers" in s and str(number) in [str(x) for x in (s.get("numbers") or [])]:
            hits.append(sid)
        elif "range" in s and in_range(number, s.get("range")):
            hits.append(sid)
    return hits


def find_dupes(items):
    """Linear-time duplicate finder."""
    seen, dupes = set(), set()
    for x in items:
        (dupes if x in seen else seen).add(x)
    return dupes


# ---- v0.3 validation -----------------------------------------------------------

def iter_nodes(manifest):
    """Yield (node, is_base) for every base set and subset, recursively. Skips
    non-dict entries (schema validation reports those)."""
    def walk(node, is_base):
        if not isinstance(node, dict):
            return
        yield node, is_base
        for child in node.get("subsets", []) or []:
            yield from walk(child, False)
    for b in manifest.get("base_sets", []) or []:
        yield from walk(b, True)
    for s in manifest.get("subsets", []) or []:
        yield from walk(s, False)


def validate_v03(set_dir, schemas, rep):
    where = str(set_dir)
    set_yaml = rep.load_yaml(set_dir / "set.yaml", f"{where}/set.yaml")
    manifest = rep.load_yaml(set_dir / "manifest.yaml", f"{where}/manifest.yaml")

    rep.schema_check(f"{where}/set.yaml", set_yaml, schemas["set"])
    rep.schema_check(f"{where}/manifest.yaml", manifest, schemas["manifest"])

    # Invariant checks below assume mappings; if the top-level shape is wrong, the
    # schema_check above already reported it — stop here rather than crash.
    if not isinstance(set_yaml, dict):
        set_yaml = {}
    if not isinstance(manifest, dict):
        rep.err(where, "manifest.yaml is not a mapping; skipping invariant checks")
        return

    # set_id agreement (set.yaml <-> manifest <-> directory name)
    if set_yaml.get("set_id") != manifest.get("set_id"):
        rep.err(where, f"set_id mismatch: set.yaml={set_yaml.get('set_id')} manifest={manifest.get('set_id')}")
    if manifest.get("set_id") != set_dir.name:
        rep.err(where, f"set_id {manifest.get('set_id')} != directory {set_dir.name}")

    sid = manifest.get("set_id") or set_dir.name  # for labelling cross-set duplicates
    rep.claim_uuid(where, set_yaml.get("uuid"), f"{sid} product")

    node_ids = {}
    checklist_dir = set_dir / "checklists"
    referenced_files = set()

    for node, is_base in iter_nodes(manifest):
        nid = node.get("id")
        label = f"node {nid}"
        if isinstance(nid, str) and nid:  # guard before using as a dict key (unhashable ids)
            if nid in node_ids:
                rep.err(where, f"duplicate node id: {nid}")
            node_ids[nid] = node
        rep.claim_uuid(where, node.get("uuid"), f"{sid} {label}")

        # base-vs-subset type rule (schema also checks, but be explicit)
        if is_base and "type" in node:
            rep.err(where, f"base set {nid} must not have a type")
        if not is_base and not node.get("type"):
            rep.err(where, f"subset {nid} must have a non-empty type list")

        parallels = [p for p in (node.get("parallels") or []) if isinstance(p, dict)]

        # parallel names unique within node (filter to hashable string names)
        pnames = [p.get("name") for p in parallels if isinstance(p.get("name"), str)]
        pdupes = find_dupes(pnames)
        if pdupes:
            rep.err(where, f"{nid}: duplicate parallel names {sorted(pdupes)}")

        # checklist file
        if not isinstance(nid, str) or not nid:
            continue  # schema reports the missing/invalid id
        cl_path = checklist_dir / f"{nid}.yaml"
        if not cl_path.exists():
            rep.err(where, f"{nid}: missing checklist file checklists/{nid}.yaml")
            continue
        referenced_files.add(cl_path.name)
        rows = rep.load_yaml(cl_path, f"{where}/checklists/{nid}.yaml")
        rep.schema_check(f"{where}/checklists/{nid}.yaml", rows, schemas["checklist"])
        if not isinstance(rows, list):
            continue
        rows = [r for r in rows if isinstance(r, dict)]

        # Rows without a usable `number` are reported by schema validation; exclude
        # them from invariant checks so a missing number doesn't become the string
        # "None" and cascade into spurious dup/section errors.
        numbers = [str(r.get("number")) for r in rows if r.get("number") is not None]
        ndupes = find_dupes(numbers)
        if ndupes:
            rep.err(where, f"{nid}: duplicate card numbers within node {sorted(ndupes)[:5]}")
        for r in rows:
            rep.claim_uuid(where, r.get("uuid"), f"{sid} {nid} row {r.get('number')}")

        # declared_card_count sanity
        dcc = node.get("declared_card_count")
        if isinstance(dcc, int) and dcc != len(rows):
            rep.err(where, f"{nid}: declared_card_count {dcc} != {len(rows)} rows")

        # sections partition
        sections = node.get("sections")
        section_ids = []
        if isinstance(sections, list) and sections:
            section_ids = [s.get("id") for s in sections if isinstance(s, dict) and isinstance(s.get("id"), str)]
            if find_dupes(section_ids):
                rep.err(where, f"{nid}: duplicate section ids")
            covered = {sid: 0 for sid in section_ids}
            for n in numbers:
                hits = section_of(n, sections)
                if len(hits) == 0:
                    rep.err(where, f"{nid}: card {n} is in no section (partition gap)")
                elif len(hits) > 1:
                    rep.err(where, f"{nid}: card {n} in multiple sections {hits}")
                for h in hits:
                    covered[h] = covered.get(h, 0) + 1
            for sid, c in covered.items():
                if c == 0:
                    rep.err(where, f"{nid}: section {sid} matches no rows")

        # applies_to references
        numset = set(numbers)
        for p in parallels:
            pname = p.get("name", "<unnamed>")
            a = p.get("applies_to", "all")
            if isinstance(a, dict):
                for key in ("numbers", "except"):
                    for n in a.get(key, []) or []:
                        if str(n) not in numset:
                            rep.err(where, f"{nid}: parallel {pname} applies_to.{key} references missing number {n}")
                for sid in a.get("sections", []) or []:
                    if sid not in section_ids:
                        rep.err(where, f"{nid}: parallel {pname} applies_to.sections references undeclared section {sid}")

    # orphan checklist files (present but not referenced by any node)
    if checklist_dir.exists():
        for f in checklist_dir.glob("*.yaml"):
            if f.name not in referenced_files:
                rep.err(where, f"orphan checklist file checklists/{f.name} (no matching node id)")


# ---- v0.2 legacy validation ----------------------------------------------------

def validate_v02(set_dir, schemas, rep):
    where = str(set_dir)
    if "v2set" not in schemas or "v2card" not in schemas:
        rep.err(where, "legacy v0.2 schemas unavailable (schemas/set/v0.2 or schemas/card/v0.1 missing)")
        return
    set_yaml = rep.load_yaml(set_dir / "set.yaml", f"{where}/set.yaml")
    rep.schema_check(f"{where}/set.yaml", set_yaml, schemas["v2set"])
    for card in sorted((set_dir / "cards").glob("*.yaml")):
        data = rep.load_yaml(card, str(card))
        rep.schema_check(str(card), data, schemas["v2card"])


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
    # Legacy schemas pinned to explicit version dirs so a moving pointer never changes
    # how already-committed exploded sets are validated.
    for legacy, fname in (("v2set", "set/v0.2/schema.yaml"), ("v2card", "card/v0.1/schema.yaml")):
        p = schema_dir / fname
        if p.exists():
            schemas[legacy] = load_schema(p)

    rep = Report()
    set_dirs = sorted({p.parent for p in data_dir.rglob("set.yaml")})
    if not set_dirs:
        print(f"no sets found under {data_dir}")
        return 0

    for sd in set_dirs:
        try:
            if (sd / "manifest.yaml").exists():
                fmt = "v0.3"
                validate_v03(sd, schemas, rep)
            elif (sd / "cards").is_dir():
                fmt = "v0.2"
                validate_v02(sd, schemas, rep)
            else:
                fmt = "?"
                rep.err(str(sd), "no manifest.yaml (v0.3) or cards/ (v0.2)")
        except Exception as e:  # pragma: no cover - a bad set must not abort the run
            fmt = "!"
            rep.err(str(sd), f"unexpected error during validation: {e}")
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
