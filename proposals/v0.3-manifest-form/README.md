# OCP v0.3 — the manifest (compact generating form)

**Status:** draft for review (2026-07-06). Supersedes the exploded one-file-per-card layout.

## Why

The v0.2 layout commits every parallel of every card as its own file. Real proof:
2026 Bowman (PR #19) = **17,928 card files**, where all variants of a card are
identical except `uuid`, a per-parallel-constant `print_run`/`serial_numbered`, and
templated `card_name`/`description`/`image_url` (17,928 *fabricated* placeholder
image URLs). No human can review that.

v0.3 commits the **compact generating form** and derives the explosion at consume
time. 2026 Bowman collapses from **17,928 files → ~4 readable ones**.

## Layout

```
data/<genre>/<set-id>/
  set.yaml                 # set-level metadata + source attribution (what it IS)
  manifest.yaml            # subsets + parallels (the generating STRUCTURE)
  checklists/
    base.yaml              # committed row identities for subset `base`
    bowman-scouts-top-100.yaml
    chrome-prospect-autographs.yaml
    ...                    # one file per subset id
```

- **set.yaml** — descriptive metadata. No parallels, no card counts (derived).
- **manifest.yaml** — the list of subsets; each subset declares its `kind`, its
  declared base-checklist size (a review check), and its `parallels`.
- **checklists/&lt;subset-id&gt;.yaml** — an array of rows (`number → subjects`), each
  with a **committed `uuid`** (the canonical, shared card identity). One file per
  subset; the filename matches the subset `id`.

## What is committed vs. derived

| Thing | Committed? | How |
|---|---|---|
| set `uuid` | ✅ committed | minted by tcapi (identity authority), published here |
| base checklist row `uuid` | ✅ committed | the canonical card identity — stable forever |
| entity `ref` (player/team UUID) | ✅ referenced | owned by tcapi; resolution populates it |
| **parallel card `uuid`** | ❌ **derived** | `uuidv5(base_row.uuid, parallel.name)` — see IDENTITY.md |
| `card_name` / `description` | ❌ derived | composed at display time from subject + subset + parallel |
| `image_url` | ❌ enrichment | keyed by card uuid, added later — never fabricated |
| total `card_count` | ❌ derived | expansion count; the review report checks it |

## Consume-time expansion (deterministic)

```python
# pseudocode — runs in the consumer/CI, output goes to tcapi. Nothing persisted in OCP.
for subset in manifest.subsets:
    rows = load(f"checklists/{subset.id}.yaml")
    for row in rows:
        emit_card(uuid=row.uuid, subset=subset, parallel=None, row=row)   # the base card (committed uuid)
        for p in subset.parallels:
            if applies(p, row):                                           # applies_to: all | numbers[...]
                emit_card(
                    uuid = uuidv5(row.uuid, p.name),                      # DERIVED, reproducible everywhere
                    subset = subset, parallel = p, row = row,
                    print_run = p.print_run, serial_numbered = p.serial_numbered,
                )
```

`emit_card` maps OCP fields → tcapi's card schema and upserts by `uuid` (idempotent
re-sync). Because every uuid is deterministic, re-running produces byte-identical
identities — an update is an update, never a duplicate.

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
