---
name: falsify-bundle
description: Where a whole pool of file-bundle deliverables is wrong together — the filename the task stated and nobody used, the derivable breakdown nobody surfaced, the exclusion applied on too broad a basis, the status column collapsed into one count. One check per entry, run against the task's wording and the source data.
applies-to: *.docx, *.pptx, *.csv, *.html, *.txt, *.doc
phase: fals
---

# Where file bundles are wrong together

These tasks are graded item by item against a rubric of things the deliverable must state
or contain. A pool rarely computes anything wrong; it omits, over-aggregates, or files the
work under the wrong name. Check the bundle against the task's own words and against the
source data, not against the other candidates.

## The contract the task states

1. **Compare the delivered filename byte for byte against the task's stated output.** When
   the prompt carries a "Required output files" line, or names the file inline, that string
   is the contract. A pool that named the file after the content it produced —
   descriptive, sensible, and not what was asked — fails on the name alone. `ls` every
   bundle against the stated list; `find` for the exact required name and confirm nothing
   returns.
2. **Check the file type, count and location too**, along with any stated length, language,
   or "preserve the original formatting" instruction. These are cheap and a whole pool
   misses them together.
3. **Scope the content to what was requested.** Material beyond the requested statistics is
   not a bonus when the task enumerates what to extract; grep the deliverable for topics the
   task never named.

## What the source data yields and nobody reported

4. **Run the standard aggregations yourself and check each appears in the deliverable.**
   Value-counts by every categorical column the task names, per-group rates using the
   denominator the workspace provides, month-by-month breakdowns for the entity the task
   singles out. Where every graded figure is trivially derivable and the pool simply never
   surfaced it, there is no computational fork to find — only a coverage gap, and it is
   found by computing the obvious things and looking for them in the text.
5. **Cross-reference every quantity row of every source file against the deliverable.** A
   row that never becomes a line item, a bid entry, or a reconciliation entry is the orphan
   the pool dropped.
6. **Every named source contributes facts. List them and confirm each one landed.** When
   the brief points at a file, enumerate what that file uniquely supplies and check the
   deliverable carries it.

## Aggregation and exclusion basis

7. **A distinct status value in the data is a distinct column in the report.** When the
   source has both "Absent" and "Partial Absence" and the brief lists total absences and
   total partial absences as separate figures, folding partials into the absence count is
   the shared error. Recompute each count on the literal status value.
8. **An exclusion applies only where its own record reaches.** A blanket leave window does
   not excuse every absence inside it — match each exclusion to the specific dates and the
   specific reason its record names, and do not deduct leave that covers a day the primary
   count already excluded.
9. **Two independent parameter ranges make a grid, not a diagonal.** Enumerate the cross
   product unless the task pairs them explicitly.
10. **Read the scope word in the task sentence.** "The" statistic over "all" records is one
    number; a per-group table is not it. A threshold computed per segment is not the
    threshold over the whole set when the task says "the" threshold.

## When you cannot settle it

A fork you found and cannot decide is worth more written down than resolved by taste.
Record both readings and say in `result` what would settle it.
