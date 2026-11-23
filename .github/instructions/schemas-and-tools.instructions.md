---
applyTo: "schemas/**,tools/**"
---

# Reviewing schemas and tools

A PR that changes `schemas/` or `tools/` is not a set PR. `CONTRIBUTING.md` keeps tooling and schema changes out of data PRs, so flag a data PR that touches either.

## Schemas

- `schemas/IDENTITY.md` is a frozen spec. Treat any edit as a versioned migration and say so. Do not accept it as a wording tweak.
- Each schema versions on its own, keyed to what validates (`schemas/README.md` "Versioning"). A major or minor change gets a new `vX.Y/` directory, and the `schema.yaml` and `README.md` pointer symlinks are repointed to it. A patch change is edited in place.
- Every schema change is recorded in that schema's `CHANGELOG.md`.
- Keep the "Current Versions" table in `schemas/README.md` and the top-level `README.md` version text in step with the repointed symlinks. A stale version there is a real finding.

## Tools

- Tools stay generic. Behavior is driven by arguments, config or input data, never by constants for one set, URL or filename (`CONTRIBUTING.md` "Tooling contributions").
- `tools/validate.py` is a CI gate and must be defensive. Malformed input must produce a schema error in the report, not an exception. A `TypeError` on malformed section data is a real finding.
- This repo has no expansion step. Do not ask for one.
