---
name: produce-set
description: Stage A producer. Takes one Ready set work order (cardtechie/open-checklist-project#<n>), fetches its source, authors the set (the base set and every Discover-listed subset) in the v0.3 manifest form, and opens one PR, or stops and comments on the work order. Never invents rows, never merges, never closes the work order.
---

# Produce a set from a work order

The procedure is [`docs/PRODUCER.md`](../../../docs/PRODUCER.md). Read it and run it in
full, from the input gate through the report; this skill adds no rule of its own.
Author every subset the Discover block lists, run the subset gate in step (d) before
opening the PR, and stop with `subsets-unauthorable` when one cannot be authored; the
contract is in the doc, not here.

The docs are agent-neutral so that Claude Code, Codex and other agents follow the same
contract (see [`AGENTS.md`](../../../AGENTS.md)). If a rule is missing or wrong, change the
doc, not this file.
