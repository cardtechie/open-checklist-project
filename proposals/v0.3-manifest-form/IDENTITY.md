# OCP Identity & UUID Derivation — FROZEN SPEC

**Version:** 1.0 (draft, 2026-07-06). **Once published, this contract cannot change
without breaking every downstream consumer.** Treat edits as a versioned migration.

Canonical UUIDs are OCP's public interoperability primitive: the same set/card means
the same UUID for every consumer. Three ways a UUID comes to exist:

## 1. Minted (committed)

Assigned once by the identity authority (**tcapi**) and committed verbatim in OCP.
Applies to:

- **set** `uuid` (in `set.yaml`)
- **base checklist row** `uuid` (each row in `checklists/<subset>.yaml`)
- **entities** — player/team/attribute UUIDs, referenced via `subject.ref` /
  `team.ref`. Owned entirely by tcapi (see the identity/resolution workstream).

Minted UUIDs are UUIDv4 (random). They never change. In particular a row's `uuid` is
**stable under renumbering**: if a card's `number` is later corrected, keep the
`uuid` and change only `number` — identity does not move.

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
  (e.g. correcting an `except`) makes a card appear/disappear but never changes any
  other card's UUID. Re-sync stays idempotent.
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

## 3. Nested parallels

A subset that is itself an insert (`kind: insert`, etc.) has its **own** committed
checklist rows with their own minted `uuid`s. Its parallels derive off *those* row
uuids by the exact same rule — the derivation is uniform across all subset kinds.

## Invariants (enforced by the validation gate)

1. `parallels[].name` MUST be unique within a subset (else two parallels collide to
   one UUID).
2. A checklist row `uuid` MUST be present and a valid UUID before expansion.
3. Row `uuid` MUST NOT be reused across rows or across sets.
4. Changing `number`, `subjects`, or any field on a row MUST NOT change its `uuid`.
5. Renaming a `parallels[].name` DOES change that parallel's derived UUIDs — treat a
   rename as a breaking identity change, not a typo fix.
6. Every card number listed in a parallel's `applies_to.numbers` or `applies_to.except`
   MUST exist in that subset's base checklist. A reference to a nonexistent number is
   a hard error — it catches typos and silent no-ops (an `except` that excludes
   nothing, a `numbers` that includes nothing).

## Namespace constant

Base/entity UUIDs are minted, not derived, so no global namespace constant is
required for card identity. Should a future version ever derive a base UUID, the
frozen namespace to use is defined here first:

```
OCP_NAMESPACE = "<CHOOSE-ONCE-AND-FREEZE-BEFORE-FIRST-PUBLISH>"   # UUIDv4, placeholder
```
