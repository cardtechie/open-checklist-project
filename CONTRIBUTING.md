# Contributing to Open Checklist Project

Thank you for helping improve the open trading card data ecosystem!

## Ways to Contribute

- Add or fix a card or set in `/data`
- Help improve the schema in `/schemas`
- Suggest or submit validation tools in `/tools`
- File issues or bugs

## Guidelines

- Follow the existing folder structure
- Validate your YAML before submitting
- Use pull requests — all changes are reviewed

## Pull request scope

To keep PRs reviewable and CI fast, scope each PR to a single concern:

- **At most one set per PR — and keep that set whole.** A pull request should
  cover no more than one set (`data/<genre>/<set-id>/`). Smaller changes are
  welcome too (fixing a card, adding a missing subset to an existing set). When
  you add a set, include all of its subsets, parallels, variations, inserts,
  autographs, and relics in the same PR — keep a set whole rather than splitting
  it across PRs by subset. Do not bundle *multiple* sets together — a single PR
  spanning many sets and tens of thousands of files cannot be meaningfully
  reviewed.
- **Keep tooling separate from data.** Changes to `/tools` or `/schemas` go in
  their own PR, not mixed with data additions. Open an issue first for new tooling.
- **Rebase, don't merge.** Keep your branch's history linear; avoid merge commits
  from `main`.

## Tooling contributions

Tools in `/tools` are welcome, but they must be **generic and reusable** by
others — not one-off scripts tailored to a single import:

- Drive behavior through **arguments, config files, or input data**, not
  hardcoded constants for specific sets, URLs, or filenames.
- A new set must be addable **without editing the script**.
- Avoid dependencies on local files that aren't in the repo (e.g. a private
  spreadsheet on your machine).
- Prefer tools that **validate, transform, or consume** the published data over
  one-off generators used to produce a single contribution. Keep that kind of
  personal scaffolding in your own fork.

## Bulk and generated imports

Large, machine-generated checklists are welcome, with a few expectations:

- Submit them **one set at a time** (see above).
- Record where the data came from, in the data itself: a `metadata.source_name`
  / `source_url` on the set, and per-card `external_links` pointing to the
  source. Raw source files (e.g. spreadsheets) should **not** be committed —
  keep them out via `.gitignore`.
- Generated parallels and variations are accepted on a best-effort basis. As an
  open-data project, accuracy is refined over time through follow-up corrections,
  so initial imports do not need every record independently verified.
- Use real `image_url`s where available; omit the field rather than committing
  placeholder URLs.