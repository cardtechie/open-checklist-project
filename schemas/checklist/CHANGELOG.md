## [v0.1] - 2026-07-09
- Initial release of the checklist schema (v0.3 "manifest form").
- Array of committed rows: `number` + `uuid` (required), optional `title`,
  `description`, `subjects`, `rookie_card`, `variation`, `notes`.
- A subject is a combination of `entities`, each `{ role, name, ref }` — `role` is an
  open vocabulary; entity type/identity lives in tcapi (`ref`).
- Card names and parallels are derived, not committed.
