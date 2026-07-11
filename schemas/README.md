# Schemas

YAML schemas for the Open Checklist Project data structures.

As of **v0.3**, a set is stored in the **manifest form**: a compact *generating*
structure (base checklists + a manifest) from which the full per-card explosion is
**derived at consume time**. This replaces the earlier exploded layout that committed
one file per card × parallel. Both formats validate (see [Validation](#validation)) so
legacy data isn't broken during migration.

## Current Versions

| Schema | Version | Schema file | Docs |
|---|---|---|---|
| **Set** | v0.3 (manifest form) | [`set/schema.yaml`](set/schema.yaml) | [set/README.md](set/README.md) |
| **Manifest** | v0.2 | [`manifest/schema.yaml`](manifest/schema.yaml) | [manifest/README.md](manifest/README.md) |
| **Checklist** | v0.1 | [`checklist/schema.yaml`](checklist/schema.yaml) | [checklist/README.md](checklist/README.md) |
| **Card** | v0.1 (legacy, exploded) | [`card/schema.yaml`](card/schema.yaml) | [card/README.md](card/README.md) |

The identity/UUID contract that spans the manifest form (which UUIDs are committed vs.
derived, and the cross-file invariants) is the frozen spec in [`IDENTITY.md`](IDENTITY.md).

## The manifest form (v0.3)

A set directory holds three kinds of file:

```
data/<genre>/<set-id>/
  set.yaml                    # descriptive product / umbrella metadata  (Set schema v0.3)
  manifest.yaml               # the generating structure                 (Manifest schema)
  checklists/<node-id>.yaml   # committed row identities, one file/node   (Checklist schema)
```

- **`set.yaml`** — descriptive product metadata only. Its `uuid` is the product's; each
  base set carries its own `uuid` in the manifest.
- **`manifest.yaml`** — `base_sets[]` (the roots) plus optional product-level
  `subsets[]` (inserts not tied to a base set). A base set and a subset are the **same
  recursive node** — own checklist, `parallels`, optional `sections`, and child
  `subsets` — differing only in that a base set has no `type` and a subset carries a
  `type` list (`insert` / `autograph` / `relic` / `variation`, which can combine, e.g.
  `[autograph, relic]`).
- **`checklists/<node-id>.yaml`** — the committed rows for one node (`number` + `uuid`
  + `subjects`). One file per node id.

The per-card parallel explosion is **derived** at consume time
(`uuidv5(row.uuid, parallel.name)`) and **never committed** — a full product collapses
from tens of thousands of files to a handful. See [`IDENTITY.md`](IDENTITY.md) for the
derivation rules and [manifest/README.md](manifest/README.md) for `parallels`,
`applies_to`, and `sections`.

### Legacy exploded format (v0.2)

Earlier sets use `data/<genre>/<set-id>/set.yaml` (Set schema **v0.2**) plus
`cards/*.yaml` (Card schema **v0.1**), one file per card and per parallel. The validator
still accepts this format for sets that haven't been migrated.

## Directory Structure

```
schemas/
├── IDENTITY.md          # frozen identity/UUID contract for the manifest form
├── set/
│   ├── schema.yaml      # symlink -> v0.3/schema.yaml (current)
│   ├── README.md        # symlink -> v0.3/README.md
│   ├── CHANGELOG.md
│   └── v0.1/ · v0.2/ · v0.3/   # version-specific schema.yaml + README.md
├── manifest/
│   ├── schema.yaml      # symlink -> v0.2/schema.yaml (current)
│   ├── README.md · CHANGELOG.md
│   └── v0.1/ · v0.2/
├── checklist/
│   ├── schema.yaml      # symlink -> v0.1/schema.yaml
│   ├── README.md · CHANGELOG.md
│   └── v0.1/
└── card/                # legacy (exploded format)
    ├── schema.yaml      # symlink -> v0.1/schema.yaml
    ├── README.md · CHANGELOG.md
    └── v0.1/
```

Each schema type is a directory with a `schema.yaml` pointer symlink to the current
version, a `README.md` (also a symlink to the current version's docs), a `CHANGELOG.md`,
and versioned `v0.X/` subdirs.

## Versioning

Each schema versions independently, following semantic versioning **keyed to what
validates** — the only thing worth pinning a schema to is its validation behavior.

| Level | Meaning | Examples | Old data still valid? |
|---|---|---|---|
| **major** (`v0.x → v1.0`) | **Breaking** — data valid under the old schema can become invalid, or a field's meaning changes | add a required field, remove/rename a field, tighten a constraint | ❌ needs migration |
| **minor** (`v0.1 → v0.2`) | **Backward-compatible** schema change | new optional field, **relax a constraint**, new enum value, new allowed shape | ✅ |
| **patch** | **No validation change** — text only | fix a description/comment/example, wording, typos | ✅ (nothing changed) |

**Directory policy:**

- **major and minor changes get a new version directory** (`v0.2/`), because a consumer
  may pin to a specific validation contract. Repoint the `schema.yaml` (and `README.md`)
  symlink to the new version; keep the old directory as history. `$schema_version` in the
  schema is the `major.minor` (e.g. `"0.2"`).
- **patch changes do NOT get a directory** — edit the current version's files in place and
  record the change in that schema's `CHANGELOG.md` with a date. Nothing pins to a doc
  fix, so a patch directory would be churn for a change that doesn't affect validation.

Rule of thumb: **if a document's validity could change, it's at least a minor bump (new
directory); if only the prose changed, it's a patch (in place).**

## Validation

```bash
python tools/validate.py
```

The validator discovers every set under `data/` and, per set directory, detects the
format — **manifest form** (a `manifest.yaml` is present) or **legacy exploded**
(a `cards/` directory) — and validates against the matching schemas. Current-version
schemas are loaded via the `schema.yaml` pointer symlinks; the legacy v0.2 set schema is
loaded from its explicit version directory.

Beyond JSON-Schema validation, the manifest form also enforces the cross-file invariants
from [`IDENTITY.md`](IDENTITY.md) that schema alone can't express — e.g. globally-unique
committed UUIDs, unique node ids, checklist-file presence with no orphans,
base-has-no-type / subset-has-a-type-list, per-node parallel and card-number uniqueness,
`declared_card_count` matching the row count, `sections` partitioning the checklist, and
`applies_to` references resolving to existing rows / sections.

To validate against a specific version explicitly:

```python
schema = load_schema("schemas/set/v0.2/schema.yaml")
```

## Version History

### Set ([changelog](set/CHANGELOG.md))
- **v0.3** ([schema](set/v0.3/schema.yaml), [docs](set/v0.3/README.md)) — manifest form; set.yaml is descriptive product metadata (structure/parallels/checklists moved to the manifest + checklists).
- **v0.2** ([schema](set/v0.2/schema.yaml), [docs](set/v0.2/README.md)) — required `genre`/`category`, enhanced temporal handling.
- **v0.1** ([schema](set/v0.1/schema.yaml), [docs](set/v0.1/README.md)) — initial set structure.

### Manifest ([changelog](manifest/CHANGELOG.md))
- **v0.2** ([schema](manifest/v0.2/schema.yaml), [docs](manifest/v0.2/README.md)) — `base_sets` optional (`anyOf(base_sets | subsets)`), for base-less products.
- **v0.1** ([schema](manifest/v0.1/schema.yaml), [docs](manifest/v0.1/README.md)) — initial manifest schema: base_sets + product-level subsets, recursive nodes, parallels/`applies_to`, sections, list `type`.

### Checklist ([changelog](checklist/CHANGELOG.md))
- **v0.1** ([schema](checklist/v0.1/schema.yaml), [docs](checklist/v0.1/README.md)) — initial checklist schema: committed rows with `subjects` as combinations of `entities`.

### Card ([changelog](card/CHANGELOG.md)) — legacy
- **v0.1** ([schema](card/v0.1/schema.yaml), [docs](card/v0.1/README.md)) — initial card schema for the exploded format.

---

For field-level detail, see each schema's own README (linked above). For questions or
contributions, refer to the main Open Checklist Project repository.
