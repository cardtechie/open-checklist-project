---
name: discover-work-order
description: Stage A Discover. Takes one set work order (cardtechie/open-checklist-project#<n>), resolves its identity and checklist sources, and posts the Discover block so the work order passes tools/check_work_order.py and the produce-set job can start. Never guesses a source, never invents an identity, never overwrites a value already set.
---

# Discover a work order

The procedure is [`docs/DISCOVER.md`](../../../docs/DISCOVER.md). Read it and run it in
full, from the input gate through the report; this skill adds no rule of its own.

The docs are agent-neutral so that Claude Code, Codex and other agents follow the same
contract (see [`AGENTS.md`](../../../AGENTS.md)). If a rule is missing or wrong, change the
doc, not this file.
