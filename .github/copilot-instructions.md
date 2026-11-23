# Copilot code review instructions

**Review set PRs as staged data, not as code.** This repo is schemas, curated set data and a validator. Most of a set PR is source-derived YAML that no reviewer is expected to re-verify row by row.

## What this repo is

- YAML schemas in `schemas/`, curated set data in `data/`, and the validator and gate tools in `tools/`.
- It contains **no expansion, sync or consumer code**. Expansion of a checklist into cards happens downstream (`schemas/IDENTITY.md`, invariant 10). Do not ask for it here.
- Rules live in [`AGENTS.md`](../AGENTS.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`docs/PRODUCER.md`](../docs/PRODUCER.md) and [`schemas/IDENTITY.md`](../schemas/IDENTITY.md). Do not invent rules those files do not state.

## What a set PR is

- One set directory `data/<sport>/<set-id>/` in the v0.3 manifest form: `set.yaml`, `manifest.yaml` and `checklists/<node-id>.yaml`. The per-card explosion is derived and never committed, so do not ask for card files.
- It is produced from a work order issue (the Discover block) under the Stage A contract in `docs/PRODUCER.md`.
- The PR body carries `Closes #<work order>`, the source URLs with stated against authored counts, and the review report's *Subset completeness* result.
- It adds exactly one `changelog.d/<work order>-added.md` fragment, makes no `tools/` or `schemas/` change, and never edits `CHANGELOG.md`.

## Staged delivery and split PRs

- A set moves through Stage A (produce), then B (Validate), then C on the Set Pipeline board. One PR is not the whole pipeline.
- `CONTRIBUTING.md` "Pull request scope" defines the rule: a set PR may omit a Discover-listed subset when its body names the subset and links the open PR, or work order comment, that carries it under the same work order. Apply that rule as written.
- If the body names where a subset went, check that the named PR exists and carries it. Do not call the omission blocking.
- Flag a missing subset only when the body claims it is present and it is not, or when the body's counts disagree with the diff.

## The authoritative gate

- `python tools/validate.py` (the Validate Data workflow) is pass or fail. The Review Report workflow is advisory and never fails a PR.
- `tools/check_work_order.py` decides whether a work order is Ready. Subset completeness is enforced by the producer's `--require-subsets` gate and by the reviewer, because CI cannot see the Discover block.
- If CI is green, do not restate a validator check as a finding.

## Severity

- **High** only for: a changed committed `uuid`, a renamed `parallels[].name`, a likely fabricated or padded row, double expansion of a parallel, PR-body counts that contradict the diff, or an edit to `CHANGELOG.md`.
- **Medium** for a `set.yaml` metadata mismatch against the Discover block.
- Do not withhold a green verdict over a split the PR body already answers, or over data you cannot verify from the repo.
- Do not post a standing "a human must verify the N rows or print runs" note.

Path-specific rules are in `.github/instructions/`. Stop if you are about to suggest card files, expansion code, a re-check of what `validate.py` passed, or an external re-verification of source-derived rows.
