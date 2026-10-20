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
(creating the subsection when absent), deletes the fragments it consumed, and
commits the result back with `[skip ci]`.

Entries land under `[Unreleased]` because this repo cuts no tagged releases yet.
Versioned sections arrive with #82.

A fragment whose name does not match `<issue>-<type>.md`, or whose body is
empty, **fails the collation run**. It is never skipped silently, because a
skipped fragment is an entry that never reaches the changelog. Validate without
writing anything:

```bash
bash scripts/collate-changelog.sh --check
```

The `Changelog fragment` workflow runs the same check on every PR and fails a PR
that adds no fragment. Dependabot PRs are exempt.
