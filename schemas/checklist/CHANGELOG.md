## [v0.2] - 2026-11-14
- Add optional row-level `base` (boolean, default `true`). `base: false` marks a row the
  source lists only as parallels: it derives no plain card, and its parallels still derive
  from the row `uuid`. Backward compatible; all v0.1 data remains valid.

## [v0.1] - 2026-07-09
- Initial release of the checklist schema (v0.3 "manifest form").
- Array of committed rows: `number` + `uuid` (required), optional `title`,
  `description`, `subjects`, `rookie_card`, `variation`, `notes`.
- A subject is a combination of `entities`, each `{ role, name, ref }` — `role` is an
  open vocabulary; entity type/identity is resolved externally via `ref`.
- Card names and parallels are derived, not committed.
