# Releasing

This repository is versioned with [Semantic Versioning](https://semver.org/) and published as
GitHub releases. Tags are bare version numbers with no `v` prefix: `0.1.0`, not `v0.1.0`.

## Initial version: 0.1.0

The repo is pre-1.0: the data model is still moving (manifest form v0.3, with manifest and
checklist schemas at v0.2 and v0.1). A `0.x` line says so. The first release is `0.1.0`, not
`0.3.0`, which would be confused with the Set schema version.

## What each bump means

The rules are keyed to what a consumer of the data has to do.

| Bump | When |
| --- | --- |
| **major** | A breaking change to the data contract: a schema major version, a change to the UUID/identity contract in `schemas/IDENTITY.md`, or removing a set. |
| **minor** | A backwards-compatible addition: a new set, a new schema minor version, new tooling. |
| **patch** | A correction to existing set data, or a tooling or docs fix. |

While the version is `0.x`, a breaking change bumps **minor** instead of major.

## How a release is cut

A maintainer declares the version; the collation writes it. No pull request edits
`CHANGELOG.md` by hand, a release included, so every PR follows the same fragment rule (see
[`changelog.d/README.md`](../changelog.d/README.md)). Neither workflow pushes to `main`,
because the `main` ruleset requires pull requests with no bypass actors.

1. Run the **Collate changelog** workflow (`.github/workflows/collate-changelog.yml`) by hand
   against `main`, with `release_version` set to the new version, for example `0.1.0`
   (`gh workflow run collate-changelog.yml --ref main -f release_version=0.1.0`). It runs
   `scripts/collate-changelog.sh --release X.Y.Z`, which collates every pending fragment and
   then turns the `## [Unreleased]` body into a `## [X.Y.Z] - YYYY-MM-DD` section (today's UTC
   date) under a fresh, empty `## [Unreleased]`. The result goes to the usual collate PR from
   `auto/collate-changelog`, retitled `Release X.Y.Z`; an already-open collate PR is refreshed
   rather than duplicated, so nothing pending is left out. The script refuses an empty release
   and a version that already has a section.
2. Review and merge that PR. While it is open, a plain collation run will not overwrite it;
   anything merged in the meantime is collated into the next `[Unreleased]` afterwards.
3. On the push to `main`, `.github/workflows/release.yml` reads the newest `## [X.Y.Z]`
   heading. If that tag does not exist, it creates the tag and a GitHub release whose notes
   are that section's body. If the tag exists, it does nothing, so ordinary merges are inert.
4. Check the release page: the notes should match the changelog section.

The dispatch input exists only once this workflow is on `main`, so the first release, `0.1.0`,
is cut after this process merges.

Tag creation uses the default `GITHUB_TOKEN` with `contents: write`. If a tag ruleset is ever
added to this repo, the workflow will need a token that is allowed to create tags.

The release is cut by a maintainer. Contributors add a `changelog.d/` fragment (see
[`CONTRIBUTING.md`](../CONTRIBUTING.md)) and do not choose a version.
