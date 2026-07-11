# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Open Checklist Project is an open-data initiative providing standardized trading card
checklist data. The project consists of:

- **YAML schemas** — sets, manifests, and checklists (in `schemas/`)
- **Curated data** organized by genre/sport/set (in `data/`)
- **Validation tools** to ensure data compliance (`tools/validate.py`)
- **GitHub workflows** for automated validation

## The manifest form (v0.3)

A set is stored in the **manifest form**: a compact *generating* structure from which the
full per-card explosion is **derived at consume time** (never committed). A set directory:

```
data/<genre>/<set-id>/          # e.g. data/baseball/2026-bowman/
├── set.yaml                    # descriptive product/umbrella metadata   (Set schema v0.3)
├── manifest.yaml               # the generating structure                (Manifest schema)
└── checklists/
    └── <node-id>.yaml          # committed row identities, one file/node  (Checklist schema)
```

- **`set.yaml`** — product metadata only. Its `uuid` is the product's; each base set
  carries its own `uuid` in the manifest.
- **`manifest.yaml`** — `base_sets[]` (the roots) plus optional product-level `subsets[]`
  (inserts not tied to a base set; also used by base-less products). A base set and a
  subset are the **same recursive node** — own checklist, `parallels`, optional
  `sections`, and child `subsets` — differing only in that a base set has no `type` and a
  subset carries a `type` **list** (`insert` / `autograph` / `relic` / `variation`, which
  can combine, e.g. `[autograph, relic]`).
- **`checklists/<node-id>.yaml`** — an array of committed rows (`number` + `uuid` +
  `subjects`); the filename matches the node `id`.

The per-card parallel explosion is **derived** (`uuidv5(row.uuid, parallel.name)`), never
committed — a full product collapses from tens of thousands of files to a handful. The
identity/UUID contract (which UUIDs are committed vs. derived, and the cross-file
invariants) is the frozen spec in [`schemas/IDENTITY.md`](../schemas/IDENTITY.md).

## Schemas

- **Set** v0.3 — `schemas/set/schema.yaml`
- **Manifest** v0.2 — `schemas/manifest/schema.yaml`
- **Checklist** v0.1 — `schemas/checklist/schema.yaml`

Each schema type is a directory with a `schema.yaml` pointer symlink to the current
version, a `README.md` (also a symlink to the current version's docs), a `CHANGELOG.md`,
and versioned `v0.X/` subdirs. See [`schemas/README.md`](../schemas/README.md) for the
structure, field detail, and the **versioning policy** (major / minor / patch keyed to
what validates; major & minor get a new version directory, patch is edited in place).

## Validation

```bash
# Python
pip install pyyaml jsonschema
python tools/validate.py

# Docker
docker build -t open-checklist-validator .
docker run open-checklist-validator
```

`tools/validate.py` discovers every set under `data/`. A **manifest-form** set
(has `manifest.yaml`) is validated against the manifest-form schemas (via the
`schema.yaml` pointer symlinks) and then checked for the cross-file invariants from
`IDENTITY.md` that JSON Schema alone can't express:

1. `set.yaml`, `manifest.yaml`, and every `checklists/*.yaml` are schema-valid.
2. Product / base-set / subset / row UUIDs are globally unique across the run; node ids
   are unique; every node has a `checklists/<id>.yaml` and there are no orphan files.
3. Base sets have no `type`; subsets have a non-empty `type` list.
4. Parallel names and card numbers are unique per node; `declared_card_count` matches.
5. `sections` partition a node's checklist (every row in exactly one section).
6. `applies_to` (`numbers` / `except` / `sections`) references resolve to existing rows /
   sections; `set_id` agrees across `set.yaml`, `manifest.yaml`, and the directory name.

New data must use the manifest form. The validator still accepts the earlier exploded
`cards/` format for not-yet-migrated sets, but that format is **deprecated** and being
retired (the `card` schema and the validator's exploded path are slated for removal —
see [#33](https://github.com/cardtechie/open-checklist-project/issues/33)).

## GitHub Integration

- **Validation workflow** runs on PR/push to `data/**/*.yaml` or `schemas/**/*.yaml`.
- Python 3.11 with `pyyaml` and `jsonschema`.
- Validation must pass for data changes to be accepted.

## Contributing data

New set data must use the manifest form (`set.yaml` + `manifest.yaml` + `checklists/`);
one set per PR, kept whole. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
