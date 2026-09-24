---
name: repair-record
description: Use in the repair phase when the base deliverable is a structured record (answer.json, a filled template of fields, enums and lists) computed from a database, API or data files in the workspace. How a record is graded, how to close an open field with a query or the template's own text, how to complete a derived list, and what a repair of a record must never do.
applies-to: answer.json, *.json
phase: repair
---

# Repairing a structured record

A record is graded field by field against a key: exact match on values, tokens and
list membership, at the precision the template states. A field is right or wrong on
its own; a list is right when it holds exactly the members the rule selects. There is
no partial credit for a value that is close, a token that means the same thing, or a
list that has most of the members.

## Closing an open field

A material row left open on a field is closed by one of three things, in this order:

1. **The template's own text.** Re-read — and quote — the field's description, its
   allowed values, its ordering and calculation rule in the answer template or the
   task. The literal text decides; a reading that is more coherent with the domain but
   not with the text is wrong.
2. **A policy table in the data.** `grep -rn "priority\|precedence\|threshold\|freshness\|mapping\|round"`
   over the data files; `sqlite3 <db> ".tables"` and the tables whose names match the
   field. A stated rule applies as written even where it changes nothing downstream.
3. **The computation, both ways.** When two conventions remain (compounded vs
   standalone, inclusive vs exclusive boundary, calendar vs business days), compute
   under each and look for the one the data itself uses elsewhere — the same table's
   other columns, a worked example, a prior period's stored result.

If all three are silent, the field stays as the base has it. Never blank a filled
field, never write two values, never pick the majority.

## Derived lists and dependent fields

A list field (required actions, affected IDs, flagged items) is regenerated from its
rule, not patched: run the selection again over the data and deliver the full result.
When you change a field that others depend on (a rate, a date, a status), recompute
the dependents from it; a record consistent with its own inputs is what the key holds.

## Inventory granularity

Compare the base with the uncharged candidates field by field. A field the base leaves
empty or null that others fill, and a list member others include that the base omits,
is a query away: run it, and adopt what the data returns. Values that appear in no
table, template or document — whatever the candidate — are not adopted.

## Verify

Reload the file, confirm it parses, holds the template's keys and types and nothing
else, uses the template's literal tokens and its stated precision, and that every
changed value equals what the query or computation returned.
