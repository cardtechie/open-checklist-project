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

The version is declared by a person in a pull request. The release workflow
(`.github/workflows/release.yml`) commits nothing, because the `main` ruleset requires pull
requests with no bypass actors.

1. Open a PR that moves the entries under `## [Unreleased]` in `CHANGELOG.md` into a new
   `## [X.Y.Z] - YYYY-MM-DD` section above the older ones, and leaves an empty
   `## [Unreleased]`.
2. Merge it.
3. On the push to `main`, the workflow reads the newest `## [X.Y.Z]` heading. If that tag does
   not exist, it creates the tag and a GitHub release whose notes are that section's body. If
   the tag exists, it does nothing, so ordinary merges are inert.
4. Check the release page: the notes should match the changelog section.

Tag creation uses the default `GITHUB_TOKEN` with `contents: write`. If a tag ruleset is ever
added to this repo, the workflow will need a token that is allowed to create tags.

The release is cut by a maintainer. Contributors add their entry under `## [Unreleased]` and
do not choose a version.
