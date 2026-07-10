# OCP Identity & UUID Derivation — FROZEN SPEC

**Version:** 1.0 (draft, 2026-07-06). **Once published, this contract cannot change
without breaking every downstream consumer.** Treat edits as a versioned migration.

Canonical UUIDs are OCP's public interoperability primitive: the same set/card means
the same UUID for every consumer. Three ways a UUID comes to exist:

## 1. Minted (committed)

Assigned once and committed verbatim in OCP (anchors, as opposed to derived ids).
The product is a hierarchy — one **product/umbrella** containing one or more **base
sets**, each containing recursive **subsets**, each holding **rows** — and every node
in it carries a committed anchor uuid:

- **product** `uuid` (in `set.yaml`) — the umbrella above the base sets.
- **base set** `uuid` (each entry in `manifest.base_sets[]`) — a base set is its own
  identity anchor, distinct from the product. One product may have several.
- **subset** `uuid` (each `subsets[]` node, at any nesting depth) — an insert /
  autograph / relic / variation is its own anchor.
- **checklist row** `uuid` (each row in `checklists/<node-id>.yaml`).
- **entities** — player/team/attribute UUIDs, referenced via `subject.ref` /
  `team.ref`. Resolved via a separate identity/resolution workstream.

Minted UUIDs are UUIDv4 (random). They never change. In particular a row's `uuid` is
**stable under renumbering**: if a card's `number` is later corrected, keep the
`uuid` and change only `number` — identity does not move. The same holds for a node's
`uuid` under renaming or re-parenting: the anchor is stable, the label is not.

## 2. Derived (never committed)

The mechanical parallel explosion. For a parallel `p` of a checklist row `r`:

```
parallel_card.uuid = uuidv5(namespace = r.uuid, name = p.name)
```

- `namespace` is the row's committed `uuid` (a valid UUID → valid v5 namespace).
  This binds the parallel to its specific base card.
- `name` is the manifest `parallels[].name` string, used as its **exact UTF-8 bytes**:
  no case-folding, no trimming, no Unicode normalization. Authoring must keep the
  string clean; consumers must not transform it. Both inputs are OCP-published
  canonical values, so every consumer computes the identical UUID.

**Identity depends on `(r.uuid, p.name)` and nothing else.** `print_run`,
`serial_numbered`, `applies_to`, and any future per-card attribute override are
**not** derivation inputs. Two consequences the spec commits to:

- **`applies_to` is a membership filter, not an identity input.** It selects *which*
  rows produce a derived card; adding or removing a row from a parallel's coverage
  (e.g. correcting an `except`, or a row moving between `sections`) makes a card
  appear/disappear but never changes any other card's UUID. Re-sync stays idempotent.
- **`sections` are derived membership, not identity.** A row's section is computed at
  consume time from the manifest's section declarations; it is not committed on the
  row and is not a `uuidv5` input. Re-sectioning a checklist never moves a UUID.
- **Reserved seam for exceptions.** A card present in a parallel with a *different*
  attribute (e.g. a one-off print run) can be expressed by a future additive
  `overrides` field WITHOUT an identity migration — because the override changes an
  attribute, not `(r.uuid, p.name)`. This is deliberately not built in v0.3, but the
  invariant above is what keeps it a non-breaking change when it is.

Reference implementation:

```python
import uuid
def parallel_uuid(base_row_uuid: str, parallel_name: str) -> str:
    return str(uuid.uuid5(uuid.UUID(base_row_uuid), parallel_name))
```

## 3. Uniform across the hierarchy

Derivation is **identical at every node and every depth**. A base set, an insert
subset, an autograph subset nested inside it — each has its **own** committed
checklist rows with their own minted `uuid`s, and each node's parallels derive off
*those* row uuids by the exact same `uuidv5(row.uuid, parallel.name)` rule. There is
no special case for base vs. subset, or for nesting level: a node is a node. Because
each row uuid is globally unique, parallels never collide across nodes even when two
nodes reuse the same card `number`.

## Invariants (enforced by the validation gate)

1. `parallels[].name` MUST be unique within a node (else two parallels collide to one
   UUID).
2. A checklist row `uuid` MUST be present and a valid UUID before expansion.
3. Every anchor `uuid` — product, base set, subset (any depth), and row — MUST be
   unique across the whole product; none reused across nodes or across sets.
4. Changing `number`, `subjects`, or any field on a row MUST NOT change its `uuid`;
   likewise renaming or re-parenting a node MUST NOT change the node's `uuid`.
5. Renaming a `parallels[].name` DOES change that parallel's derived UUIDs — treat a
   rename as a breaking identity change, not a typo fix.
6. Every card number listed in a parallel's `applies_to.numbers` or `applies_to.except`
   MUST exist in that node's checklist. A reference to a nonexistent number is a hard
   error — it catches typos and silent no-ops (an `except` that excludes nothing, a
   `numbers` that includes nothing).
7. **Sections partition the checklist.** `sections` is OPTIONAL; a node with none is
   one implicit section. When declared, every committed row MUST match EXACTLY ONE
   section — a row matching zero (uncovered) or more than one (overlap) is a hard
   error. Section `id`s MUST be unique within the node.
8. Every section id in a parallel's `applies_to.sections` MUST be a declared section
   of that node. (Undeclared id = hard error.)
9. Node `id`s MUST be unique across the whole manifest (base sets and subsets share
   one id-space — each maps to `checklists/<id>.yaml`). A base set carries no `type`;
   a subset MUST carry at least one type (a list; e.g. [autograph, relic] for an auto-relic).

## Namespace constant

Base/entity UUIDs are minted, not derived, so no global namespace constant is
required for card identity. Should a future version ever derive a base UUID, the
frozen namespace to use is defined here first:

```
OCP_NAMESPACE = "<CHOOSE-ONCE-AND-FREEZE-BEFORE-FIRST-PUBLISH>"   # UUIDv4, placeholder
```
