# Changelog fragments

One fragment per PR at `changelog.d/<issue>-<type>.md`, where `<type>` is one of
`added | changed | fixed | security | removed | deprecated`.

Never hand-edit `CHANGELOG.md`, and never collate inside a PR. Collation happens
once, post-merge.

Style: one imperative sentence-case line ending in a period, prefixed with the
issue in the existing layout (`- **[Issue #N]** ...`). Sub-bullets only for a
non-obvious caveat. Never restate what is in the linked issue.

## What drains this directory

A release. `scripts/collate-changelog.sh` runs from
`scripts/commit-changelog-back.sh` in `.github/workflows/release.yml`, which a
maintainer runs by hand with the version to release. It groups the pending
fragments by type into a new `## [X.Y.Z] - YYYY-MM-DD` section of
`CHANGELOG.md`, under a fresh empty `## [Unreleased]`, deletes the fragments it
consumed, and commits the result straight back to `main` as
`cardtechie-ops-bot[bot]`. The same run then tags and publishes that commit.
See `docs/RELEASING.md`.

Between releases nothing collates: fragments stay pending here, and
`## [Unreleased]` in `CHANGELOG.md` does not fill up as PRs merge. No PR ever
edits `CHANGELOG.md`, releases included (#82, #98).

A fragment whose name does not match `<issue>-<type>.md`, or whose body is
empty, **fails the release run** before anything is written. It is never skipped silently, because a
skipped fragment is an entry that never reaches the changelog. Validate without
writing anything:

```bash
bash scripts/collate-changelog.sh --check
```

The `Changelog fragment` workflow runs the same check on every PR and fails a PR
that adds no fragment, or that edits `CHANGELOG.md`. Dependabot PRs are exempt.
