# Manifest Schema v0.2

The manifest is the **compact generating structure** of a set in the v0.3 "manifest
form". It replaces the exploded one-file-per-card layout: instead of committing every
parallel of every card, a set commits its base checklists + a manifest, and the
per-card explosion is **derived at consume time** (never committed).

A set directory is:

```
data/<genre>/<set-id>/
  set.yaml                 # descriptive product metadata (see set schema v0.3)
  manifest.yaml            # THIS schema — the generating structure
  checklists/<node-id>.yaml  # committed row identities (see checklist schema)
```

## Top level

- **`set_id`** (required) — must match `set.yaml` and the directory name.
- **`base_sets`** (optional, ≥1 when present) — the root checklists of the product. A
  base set is **not** a subset: it has no `type` and is never nested. Omitted for a
  base-less product (e.g. an all-autograph/relic high-end release). A product must have
  at least one base set **or** at least one product-level subset.
- **`subsets`** (optional) — **product-level** subsets: inserts that belong to the
  product but not to any single base set (e.g. an "Anime" insert).

## Nodes (base sets and subsets share one recursive shape)

A base set and a subset are the same node: `id`, `name`, `uuid`, optional
`declared_card_count`, `sections`, `parallels`, and child `subsets`. The only
difference in role:

- a **base set** carries **no `type`** and lives in `base_sets[]`;
- a **subset** carries a **`type`** (a list — see below) and nests under a base set,
  another subset, or the product (`subsets[]`).

Each node's committed rows live in `checklists/<id>.yaml` (ids are unique across the
whole manifest).

### `type` (subsets only) — a list

`insert` and `variation` are structural; `autograph` and `relic` are material
properties that can co-occur. So `type` is a **list**:

```yaml
type: [insert]
type: [autograph]
type: [autograph, relic]      # an autograph relic / autograph patch
type: [autograph, variation]  # a variation autograph
```

### `parallels`

Each parallel declares a `name` (unique within the node), optional `print_run` /
`serial_numbered`, and an optional `applies_to`:

```yaml
parallels:
  - { name: "Black", print_run: 10, serial_numbered: true }
  - { name: "Rookie Foil", applies_to: { sections: ["rookies"] } }
```

`applies_to` selects which rows produce a derived parallel card (default `all`):

- `numbers: [...]` — only these rows;
- `except: [...]` — all rows except these;
- `sections: [...]` — all rows in the named declared section(s).

It is a membership filter only — it never affects the derived UUID
(`uuidv5(row.uuid, parallel.name)`; see `IDENTITY.md`).

### `sections`

An optional **singular** editorial partition of a node's checklist (e.g. Veterans /
Rookies): every row belongs to exactly one section. Membership is declared here and
derived onto rows at consume time (rows carry no section field):

```yaml
sections:
  - { id: veterans, name: "Veterans", range: { from: "1", to: "50" } }
  - { id: rookies,  name: "Rookies",  numbers: ["51", "US1"] }
```

Use `range` for sequential numbering, `numbers` for non-sequential / mixed-prefix.

## Validation

`tools/validate.py` enforces the schema plus the cross-file invariants from
`IDENTITY.md`: unique node ids and (product/base/subset/row) uuids, checklist-file
presence with no orphans, base-has-no-type / subset-has-a-type-list, per-node parallel
and card-number uniqueness, `declared_card_count` match, sections partition, and
`applies_to` reference integrity.
