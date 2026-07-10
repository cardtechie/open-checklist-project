# Checklist Schema v0.1

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

## Card name

Not committed. Derived from `subjects` (number + entity names, joined per genre), or
taken from `title` when present. See the manifest README and project README.
