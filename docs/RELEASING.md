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

A maintainer declares the version; the release workflow writes it. No pull request edits
`CHANGELOG.md`, including for releases, so every PR follows the same fragment rule (see
[`changelog.d/README.md`](../changelog.d/README.md)). Fragments stay pending in `changelog.d/`
between releases; a release is what drains them.

1. Run the **Release** workflow (`.github/workflows/release.yml`) by hand against `main` with
   the new version:

   ```bash
   gh workflow run release.yml --ref main -f version=0.1.0
   ```

2. The workflow mints a `cardtechie-ops-bot` GitHub App token scoped to this repository, then
   runs `scripts/commit-changelog-back.sh X.Y.Z`. That script validates every pending fragment
   (`scripts/collate-changelog.sh --check`), collates them with
   `scripts/collate-changelog.sh --release X.Y.Z` into a `## [X.Y.Z] - YYYY-MM-DD` section
   (today's UTC date) under a fresh, empty `## [Unreleased]`, and commits `CHANGELOG.md` plus
   the fragment deletions to `main` as `cardtechie-ops-bot[bot]`, with the subject
   `docs: collate CHANGELOG for X.Y.Z`. It refuses an empty release, a version that already has
   a section, and a version that is not newer than every version already in the file.
3. The commit-back is pushed straight to `main` as a fast-forward, never a force push. If the
   push is rejected, the run fails there and nothing is tagged, so a version never ships
   without its notes.
4. The workflow then creates tag `X.Y.Z` on the commit-back and a GitHub release whose notes
   are that section's body. It refuses a version whose tag already exists.
5. Check the release page: the notes should match the changelog section, and `changelog.d/`
   on `main` should hold only `README.md`.

### Ruleset dependency

The commit-back is a direct push to `main`. The repository ruleset `main` requires pull
requests, so the push is rejected unless the `cardtechie-ops-bot` App (Integration 1882441) is
listed on that ruleset as a bypass actor with mode `always`, and the App's installation
includes this repository. The org ruleset `copilot pull request` blocks only non-fast-forward
pushes, which the commit-back never is. The tag and release are created with the same App
token; if a tag ruleset is ever added, the App needs to be allowed through it too. These are
repository settings, not something a pull request can change.

### Resuming a failed release

If the run fails after the commit-back landed (for example while creating the release), re-run
the workflow with the same version. The script sees that `CHANGELOG.md` already has
`## [X.Y.Z]`, checks that `main`'s tip is its own commit-back for that version (authored by the
bot, a single parent without the section, touching only `CHANGELOG.md` and `changelog.d/`),
and reports the release as ready without collating again, so the run goes on to tag and
publish. If anything has landed on `main` since the commit-back, the resume is refused; tag and
release the commit-back by hand instead.

The release is cut by a maintainer. Contributors add a `changelog.d/` fragment (see
[`CONTRIBUTING.md`](../CONTRIBUTING.md)) and do not choose a version.
