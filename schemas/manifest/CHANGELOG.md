## [v0.1] - 2026-07-09
- base_sets is optional: a product needs at least one base set OR one product-level subset, so base-less releases (all-autograph/relic high-end products) are valid.
- Initial release of the manifest schema (v0.3 "manifest form").
- `base_sets[]` (roots) plus optional product-level `subsets[]`; base sets and subsets
  share one recursive node shape (checklist + parallels + sections + child subsets).
- Subset `type` is a list of `[insert | autograph | relic | variation]` — structural
  (insert/variation) and material (autograph/relic) tags can co-occur.
- `parallels[].applies_to`: `all` | `numbers` | `except` | `sections`.
- Optional `sections`: a singular partition of a node's checklist (`range` or `numbers`).
- The per-card explosion is derived at consume time (`uuidv5(row.uuid, parallel.name)`),
  never committed. See `IDENTITY.md` for the frozen identity contract.
