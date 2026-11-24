---
applyTo: "data/**"
---

# Reviewing set data

A set is staged data produced from a source and gated by `python tools/validate.py`. Review what the repo can show you. Do not re-derive the source.

## Verify

- **Internal consistency.** `declared_card_count` against the row count, PR-body counts against the diff, `applies_to.numbers` and `applies_to.except` against the node's checklist, and section coverage.
- **Exact source strings.** Subject and team names carry no authoring annotations such as `(no base)`, `(SP)` or bracketed notes. That kind of fact belongs in the row `notes`.
- **`set.yaml` metadata against the Discover block.** `category` repeats the sport for a sports set (`[Football]`, not `[NCAA]`). `name` matches the API set name byte for byte, because Sync resolves by name.
- **Parallel modeling.** A parallel declared on every row when the source says the rows are that parallel double-expands. A row the source lists only as parallels uses `base: false`, not a note.
- **Placeholders and padding.** Placeholder `image_url`s (`example.com`) and runs of rows that look fabricated. A count that matches only because rows were padded is the failure `docs/PRODUCER.md` exists to prevent.

## Split PRs

- Apply the rule in `CONTRIBUTING.md` "Pull request scope". A subset the body names and links to another open or merged PR, or to a work order comment that carries it, under the same work order, is not missing.
- A follow-up PR that adds one subset to an existing set directory is normal.

## Ignore

- Re-verifying source-derived players, teams and print runs against external sites.
- A standing "a human must verify N rows" note.
- Row order and YAML style.
- Anything `validate.py` already checks and passed.
- Requests for expansion, sync or consumer behavior. This repo ships schema and validator only.

## Identity invariants to enforce (`schemas/IDENTITY.md`)

- Never suggest changing a committed `uuid`. A row `uuid` survives renumbering, and a node `uuid` survives renaming and re-parenting.
- Renaming a `parallels[].name` changes derived UUIDs. Flag it as a breaking identity change, never as a typo fix.
- Parallel names are exact UTF-8 strings. Do not suggest case, trim or Unicode normalization.
- Anchor `uuid`s are unique across the product, `parallels[].name` is unique within a node, and node `id`s are unique across the manifest.
- A subset carries at least one `type`. A base set carries none.
- Every `base: false` row is covered by at least one parallel.
- An edit to `IDENTITY.md` is a versioned migration, never a wording tweak.
