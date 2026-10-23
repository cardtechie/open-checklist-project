# Changelog fragments

One fragment per PR at `changelog.d/<issue>-<type>.md`, where `<type>` is one of
`added | changed | fixed | security | removed | deprecated`.

Never hand-edit `CHANGELOG.md`, and never collate inside a PR. Collation happens
once, post-merge.

Style: one imperative sentence-case line ending in a period, prefixed with the
issue in the existing layout (`- **[Issue #N]** ...`). Sub-bullets only for a
non-obvious caveat. Never restate what is in the linked issue.

## What drains this directory

`scripts/collate-changelog.sh`, run by `.github/workflows/collate-changelog.yml`
on every push to `main`. It groups the pending fragments by type, appends them
to the matching `### <Type>` subsection of `## [Unreleased]` in `CHANGELOG.md`
(creating the subsection when absent) and deletes the fragments it consumed.

The result is not pushed to `main`: the `main` ruleset requires pull requests
with no bypass actors. Instead the workflow commits the collation to the fixed
branch `auto/collate-changelog` and opens a single PR into `main`, titled
"Collate changelog fragments". While fragments are pending it refreshes that
branch in place on every push to `main` and reuses the open PR rather than
opening another; with nothing pending it does nothing. Do not push to that
branch by hand. The entries reach `CHANGELOG.md` when the collate PR merges.

Entries land under `[Unreleased]`. A release is the same collation run with a
version: a manual run of the workflow with `release_version` set calls
`scripts/collate-changelog.sh --release X.Y.Z`, which turns the collated
`[Unreleased]` body into a `## [X.Y.Z] - YYYY-MM-DD` section under a fresh empty
`[Unreleased]`, and the collate PR carries it. No PR hand-edits `CHANGELOG.md`
to cut a release (#82). See `docs/RELEASING.md`.

A fragment whose name does not match `<issue>-<type>.md`, or whose body is
empty, **fails the collation run**. It is never skipped silently, because a
skipped fragment is an entry that never reaches the changelog. Validate without
writing anything:

```bash
bash scripts/collate-changelog.sh --check
```

The `Changelog fragment` workflow runs the same check on every PR and fails a PR
that adds no fragment, or that edits `CHANGELOG.md`. Dependabot PRs are exempt, and the collate PR is exempt
from the added-fragment requirement because it consumes fragments instead.
