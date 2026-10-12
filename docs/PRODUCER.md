# Stage A producer contract — Source → Normalize

This is the contract of record for **Stage A**, the unattended job that takes one Ready
work order, fetches its source, writes the set in the v0.3 manifest form, and opens one
pull request. Nobody is in the loop unless a named stop case fires.

The design of record is the Set Pipeline Redesign (Producer/Consumer Architecture,
2026-09-26 decision log). Under it, this repository owns the front half of the pipeline,
from Discover to Validate. This job covers `Source` and `Normalize`. `Discover`, which
makes a work order Ready, is a separate job (#78). Merge, Expand and Sync are downstream.

**There is no converter.** `tools/validate.py` is the gate, and all eight merged v0.3 sets
were hand-authored. The producer is an agent following this document. It writes
`set.yaml`, `manifest.yaml` and `checklists/*.yaml` directly against the
[v0.3 schemas](../schemas/README.md). The only code is the precondition check
(`tools/check_work_order.py`), which decides whether the job may start.

The entrypoint is the [`produce-set` skill](../.claude/skills/produce-set/SKILL.md).

## Precondition

A work order is **Ready** for this job only when all four of these hold.
`tools/check_work_order.py` checks them. When it reports `ready: false`, the job does not
start.

1. It is an **open issue in this repository whose issue type is `Work Order`**. The
   type decides this, not the `work-order` label (#79).
2. The pinned issue field **`set_id`** is non-empty, is a lowercase slug
   (`^[a-z0-9]+(-[a-z0-9]+)*$`), and no `data/*/<set_id>/` directory exists on `main`.
3. The pinned issue field **`Reserved set UUID`** is non-empty, is a valid UUID, and is not
   already used as any `uuid` under `data/` on `main`.
4. There is a **Discover block**. This is a comment whose first line is
   `<!-- ocp-discover:v1 -->`, followed by one fenced `yaml` block with at least
   `sources:`. That is one or more entries, each with:
   - `url`: an `http` or `https` URL;
   - `card_count`: the source's own stated base-set count, as a positive integer.

   Optional keys, used when present:
   - `name`: the **exact** Trading Card API set name, when the set already exists there;
   - `genre` (`Sports`, `TCG` or `Non-Sport`), `sports` (list), `category` (list) and
     `year`;
   - per source, `parallels_listed: true|false`.

   If there is more than one block, the **newest** one wins. Only a block written by a
   repository owner, member or collaborator counts. Anyone can comment on a public
   issue, and the block decides which URL is fetched and which count is trusted. The
   pinned fields stay the source of truth for `set_id` and the UUID, and the block never
   repeats them.

Worked Discover block for work order #77:

````markdown
<!-- ocp-discover:v1 -->
```yaml
name: 2025 Panini Prizm Draft Picks
genre: Sports
sports: [Football]
category: [Football]
year: 2025
sources:
  - url: https://<source>/2025-panini-prizm-draft-picks
    card_count: <the source's stated base-set count>
    parallels_listed: true
```
````

The checker prints a JSON verdict:

```bash
python tools/check_work_order.py 77            # reads the issue through the gh CLI
python tools/check_work_order.py --from-json wo.json
# exit 0 = ready, 10 = not ready, 2 = usage or read error
```

The verdict carries `ready`, `reasons`, `set_id`, `reserved_uuid`, `name` (with
`name_source`: `discover-block` or `title`), `genre`, `sports`, `category`, `year` and
`sources`. The checker never writes to GitHub.

## Procedure

**(a) Check.** Run `python tools/check_work_order.py <n>`. If it reports not ready, stop
with `precondition-unmet` and quote its `reasons`.

**(b) Fetch.** Fetch every source URL. If a source cannot be fetched or read, stop with
`source-unreachable`. Raw source files (spreadsheets, HTML) are **never committed**
(see [CONTRIBUTING](../CONTRIBUTING.md)).

**(c) Author** `data/<dir>/<set_id>/`. `<dir>` is the sport in lower case for a Sports
set (`baseball`, `football`) and the genre in lower case otherwise (`tcg`, `non-sport`).

- `set.yaml`:
  - `uuid` is the **reserved UUID, unchanged**. It is the product anchor
    ([IDENTITY.md §1](../schemas/IDENTITY.md)).
  - `set_id` is the pinned `set_id`.
  - `name` comes from the Discover block's `name`. If the block has none, use the title
    minus `[Work Order] `.
  - `genre`, `sports`, `category` and `years` come from the block or the source. In this
    repo `category` repeats the sport for sports sets (e.g. `[Baseball]`).
  - `source.name` and `source.url` record the source.
- `manifest.yaml`:
  - **Base sets** get freshly minted UUIDv4 `uuid`s and a `declared_card_count`. They
    have no `type`.
  - **Subsets** get fresh UUIDv4 `uuid`s and a `type` list (`insert`, `autograph`,
    `relic` or `variation`).
  - **`parallels`** use the exact source names, with `print_run` and `serial_numbered`
    where the source states them, and `applies_to` where a parallel covers only some
    rows.
- `checklists/<node-id>.yaml`: one file per node. Each row gets a fresh UUIDv4 `uuid` and
  the exact source subject names, with `ref:` left null.

**Never commit** exploded per-card files or parallel uuids. Parallel cards are derived
(`uuidv5(row.uuid, parallel.name)`) at consume time.

**(d) Count.** For every node, compare the number of authored rows with the count the
source states. Any difference is a stop with `count-mismatch`. **Never pad and never
trim** to make them agree.

**(e) Validate.** Run `python tools/validate.py` locally. It must pass before a PR is
opened.

**(f) Open one PR per set.** Use branch `data/<set_id>` and target `main`. The PR adds
only that set's directory, with no `tools/` or `schemas/` changes. The body says
`Closes #<work order>` and lists each source URL with its stated count against the
authored count.

## Naming for Sync

Sync (tradingcardapi-tools) resolves Trading Card API sets **by exact name**, not by OCP
uuid. It looks up the base set by product name, a subset by name under its parent, and a
parallel as the `is_parallel` child of its node's set. So:

- When the set already exists in the API, `set.yaml` `name` must equal the API set name
  **byte for byte**. This is why the Discover block carries `name`.
- Parallel and subset names are the exact source strings, with no case-folding, trimming
  or Unicode normalization ([IDENTITY.md §2](../schemas/IDENTITY.md)). Renaming a
  parallel later changes its derived UUIDs.

## Done when

`validate.py` **passes on CI** for the set directory the PR adds. That is the whole
definition of done. The producer does not judge data quality beyond that gate. The
advisory review report is for the human reviewer.

## Stop and report

The job **stops and comments on the work order** instead of guessing. It opens no PR and
invents no row. Stop reasons:

| `reason` | When |
| --- | --- |
| `precondition-unmet` | the checker reports the work order is not Ready |
| `source-unreachable` | a source URL cannot be fetched or read |
| `count-mismatch` | a node's source card count disagrees with the declared or authored count |
| `subset-type-unknown` | a subset's `type` cannot be inferred from the source |
| `base-set-judgment` | a base-set judgment call appears, e.g. whether a separately-numbered prospect run is its own base set or a section (the Donruss "Rated Prospects" 101–200 pattern) |
| `no-parallel-ladder` | the source lists no parallel ladder, so a base-only set would pass `validate.py` and still fail the work order |

The stop comment has this format:

```markdown
<!-- ocp-producer-stop:v1 -->
reason: count-mismatch

**Stage A producer stopped. No PR was opened.**

- node `base-set`: source states 100 cards, source lists 97 rows
- source: https://…
```

The first line is the marker, and the second is `reason:` with one value from the table
above. Then comes the evidence: the source figure against the authored figure, with the
node. On a re-run, **edit the existing stop comment in place** (PATCH it) instead of
adding a new one.

### Why this is stated as a failure mode, not a nicety

An agent that finds the source **three cards short** of the declared count will otherwise
**invent three cards** so the count validates. `declared_card_count` is a validator
invariant, so fabricated rows make CI go green — the gate cannot catch this. This is not
hypothetical: the 2026 Bowman conversion surfaced ~800 fabricated "Bowman Scouts Top 100"
base-parallel duplicates, and the original exploded PRs carried 17,928 fabricated
placeholder image URLs. A count mismatch is a **stop**, always.

## Scope boundary

This job ends at a green `validate.py` on a one-set PR. It never merges and never closes
the work order. Merge, Expand and Sync happen downstream. If a set's parallels need child
sets in the Trading Card API, creating them is Sync's concern, not this job's.
