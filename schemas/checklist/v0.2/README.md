# Checklist Schema v0.2

A checklist file holds the **committed row identities** for one node (a base set or a
subset) in the v0.3 manifest form. The file is an **array of rows**, and its filename
matches the node `id`: `checklists/<node-id>.yaml`.

Each row is committed once. Its parallels are **not** stored here — they are declared in
`manifest.yaml` and derived at consume time.

## Row fields

- **`number`** (required) — printed card number/identifier, a string (may be
  non-numeric, e.g. `"US1"`, `"BCP-1"`). Unique within the node.
- **`uuid`** (required) — canonical card identity (UUID v4), committed here. Stable
  forever, including under renumbering.
- **`subjects`** (optional) — who/what the card is about. Zero or more subjects; each
  subject is a **combination of `entities`** (the combination *is* the subject):

  ```yaml
  subjects:
    - entities:
        - { role: player, name: "Shohei Ohtani",       ref: null }
        - { role: team,   name: "Los Angeles Dodgers", ref: null }
  ```

  `role` is an **open vocabulary** (player, team, coach, creature, character, …) — the
  entity's *type* lives in the entity registry, and `ref` references the canonical
  entity UUID (populated by resolution; `null` = unresolved). New genres add roles
  without a schema change.

- **`title`** (optional) — explicit card name, only when it can't be derived from
  subjects (e.g. `"Checklist"`, `"Home Run Leaders"`). Otherwise the card name is
  derived (`"<number> <subject> - <team>"`).
- **`description`** (optional) — card blurb / flavor text.
- **`rookie_card`** / **`variation`** / **`notes`** (optional) — per-card intrinsics.
- **`base`** (optional boolean, default `true`) — whether the row has a plain card. See
  [Parallel-only rows](#parallel-only-rows-base-false).

## Card name

Not committed. Derived from `subjects` (number + entity names, joined per genre), or
taken from `title` when present. See the manifest README and project README.

## Parallel-only rows (`base: false`)

Every checklist row is its node's implicit base card, and a parallel with no
`applies_to` covers every row. So a row the source lists only as parallels (no plain
version exists) would still derive a plain card that does not exist. Mark such a row
`base: false`:

```yaml
- number: "PA-7"
  uuid: 4f0c2a8e-9d51-4c3b-8a7e-2b6f1d0e5c91
  base: false          # no plain card; only the parallels below exist
  subjects:
    - entities:
        - { role: player, name: "Example Player", ref: null }
```

Semantics:

- A `base: false` row derives **no plain card**. Its parallels derive exactly as for any
  other row (`uuidv5(row.uuid, parallel.name)`), so the row's `uuid` is unchanged and
  remains the namespace for those parallels.
- At least one parallel in the node MUST cover the row (via `applies_to`: `all`,
  `numbers`, `except`, `sections`). A `base: false` row covered by no parallel would
  produce no card at all, so `tools/validate.py` rejects it.
- Omitting `base` (or `base: true`) is the default and unchanged from v0.1.

## Changes from v0.1

Backward-compatible minor: adds the optional `base` field. All v0.1 data is valid.
