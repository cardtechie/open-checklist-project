# OCP v0.3 — the manifest (compact generating form)

**Status:** draft for review (updated 2026-07-09). Supersedes the exploded one-file-per-card layout.

## Why

The v0.2 layout commits every parallel of every card as its own file. Real proof:
2026 Bowman (PR #19) = **17,928 card files**, where all variants of a card are
identical except `uuid`, a per-parallel-constant `print_run`/`serial_numbered`, and
templated `card_name`/`description`/`image_url` (17,928 *fabricated* placeholder
image URLs). No human can review that.

v0.3 commits the **compact generating form** and derives the explosion at consume
time. 2026 Bowman collapses from **17,928 files → a handful of readable ones** (a
`set.yaml`, a `manifest.yaml`, and one checklist per base set / subset).

## Layout

```
data/<genre>/<set-id>/
  set.yaml                 # PRODUCT metadata + source attribution (what it IS)
  manifest.yaml            # base_sets + subsets + parallels (the generating STRUCTURE)
  checklists/
    bowman.yaml            # committed row identities for base set `bowman`
    bowman-scouts-top-100.yaml
    bowman-chrome-prospects.yaml
    chrome-prospect-autographs.yaml
    ...                    # one file per node id (base set OR subset)
```

- **set.yaml** — descriptive **product / umbrella** metadata. No parallels, no card
  counts (derived). Its `uuid` is the product's; each base set has its own.
- **manifest.yaml** — `base_sets[]` (**one or more** roots) plus, under each, recursive
  `subsets[]`. A base set and a subset are the **same node shape** — own checklist,
  `parallels`, optional `sections`, and child `subsets` — differing only in that a base
  set has no `type` and a subset carries one (`insert`/`autograph`/…). `sections` is a
  singular editorial partition of a node's checklist (e.g. Veterans / Rookies), declared
  as a `range` or explicit `numbers` and derived onto rows at consume time; a parallel
  can target one via `applies_to.sections`.
- **checklists/&lt;node-id&gt;.yaml** — an array of rows (`number → subjects`), each with a
  **committed `uuid`** (the canonical, shared card identity). One file per node; the
  filename matches the node `id` (base set or subset — they share one id-space).

## What is committed vs. derived

| Thing | Committed? | How |
|---|---|---|
| product `uuid` (set.yaml) | ✅ committed | the umbrella; minted by tcapi (identity authority) |
| base set / subset `uuid` (each node) | ✅ committed | each node is its own anchor — minted by tcapi |
| checklist row `uuid` | ✅ committed | the canonical card identity — stable forever |
| entity `ref` (in a subject) | ✅ referenced | owned by tcapi; resolution populates it |
| **parallel card `uuid`** | ❌ **derived** | `uuidv5(row.uuid, parallel.name)` — see IDENTITY.md |
| card `name` | ❌ derived / ✅ `title` | derived from `subjects` (see below); the optional row `title` overrides |
| card `description` | ✅ committed (optional) | explicit blurb on the row, when a card has one |
| `image_url` | ❌ enrichment | keyed by card uuid, added later — never fabricated |
| total `card_count` | ❌ derived | expansion count; the review report checks it |

## Consume-time expansion (deterministic)

```python
# pseudocode — runs in the consumer/CI, output goes to tcapi. Nothing persisted in OCP.
# One recursive walk handles base sets, subsets, and any nesting — a node is a node.
for base_set in manifest.base_sets:
    expand(base_set)

def expand(node):
    rows = load(f"checklists/{node.id}.yaml")
    sections = section_of(node, rows)                                      # {row.number: section_id}, derived
    for row in rows:
        emit_card(uuid=row.uuid, node=node, parallel=None, row=row,
                  section=sections.get(row.number))                       # section is DERIVED, not committed
        for p in node.get("parallels", []):
            if applies(p, row, sections):                                 # membership filter, below
                emit_card(
                    uuid = uuidv5(row.uuid, p.name),                      # DERIVED, reproducible everywhere
                    node = node, parallel = p, row = row,
                    print_run = p.print_run, serial_numbered = p.serial_numbered,
                )
    for child in node.get("subsets", []):                                 # recurse — same rule at every depth
        expand(child)

def applies(p, row, sections):
    a = p.get("applies_to", "all")
    if a == "all":        return True
    if "numbers"  in a:   return row.number in a["numbers"]          # ONLY these rows
    if "except"   in a:   return row.number not in a["except"]       # all rows EXCEPT these
    if "sections" in a:   return sections.get(row.number) in a["sections"]  # rows in these sections
```

`applies_to` only gates *whether* a row emits a parallel card — it is never an input
to `uuidv5`. So an exception adds/removes a card without moving any other uuid, and
re-sync stays idempotent.

`emit_card` maps OCP fields → tcapi's card schema and upserts by `uuid` (idempotent
re-sync). Because every uuid is deterministic, re-running produces byte-identical
identities — an update is an update, never a duplicate.

## Card name derivation

A card's display name is **derived** from its row, never committed — unless the row
carries an explicit `title`, which wins. The rule composes the parts that exist:

- prefix the row `number`;
- render each **subject** by joining its `entities`' names (sports: a `player` + a
  `team` → "Name - Team");
- join multiple subjects with " / ".

| Row | Derived name |
|---|---|
| #2 · subject [player "Shohei Ohtani", team "Los Angeles Dodgers"] | `2 Shohei Ohtani - Los Angeles Dodgers` |
| #10 · subject [player "Shohei Ohtani"] | `10 Shohei Ohtani` |
| #5 · subject [team "Los Angeles Dodgers"] | `5 Los Angeles Dodgers` |
| #50 · two subjects | `50 A - TeamA / B - TeamB` |
| #300 · no subjects, `title: "Checklist"` | `300 Checklist` |

The separator/format ("player - team") is **genre-specific display logic**, not schema:
the row just stores `entities` + their `role`s. Adding TCG/non-sport adds new `role`
values (creature, character, …), not new fields — the card schema stays stable.

## Review report (separate artifact, not built here)

The manifest form is what makes the computed review report possible: base counts vs.
declared, numbering gaps, duplicate parallel names, print-run sanity — all read from
a handful of files at editorial altitude. Spec'd separately.

## Files in this draft

- `schemas/set.v0.3.schema.yaml`
- `schemas/manifest.v0.1.schema.yaml`
- `schemas/checklist.v0.1.schema.yaml`
- `IDENTITY.md` — the frozen UUID-derivation spec
- `example/2026-bowman/` — a folded, abbreviated worked example
