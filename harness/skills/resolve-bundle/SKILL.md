---
name: resolve-bundle
description: How to settle a split between bundles of office files - what counts as deciding evidence when candidates differ in file names and formats, in how they counted or aggregated the source data, or in what they included. The task's stated contract and the source data's own categories decide; polish and volume do not.
applies-to: *.docx, *.pptx, *.csv, *.html, *.txt, *.doc
phase: elim
---

# Settling a split between file bundles

## The contract

1. **The task's stated output is the contract, byte for byte.** Where the prompt names the
   required files, a candidate whose file carries that exact name, type and location meets
   it and one with a descriptive, sensible, different name does not. The same goes for a
   stated length, language or "preserve the original formatting".
2. **Scope is part of the contract.** When the task enumerates what to extract or report,
   the candidate that delivers those items is not outranked by one that delivers more.

## The basis of a count

3. **A distinct status value in the data is a distinct figure in the report.** Where
   candidates differ because one folded "Partial Absence" into "Absent", recompute each count
   on the literal value and see which the brief lists separately.
4. **An exclusion applies only where its own record reaches.** Match each exclusion to the
   dates and the reason its record names; a blanket window is the usual source of the
   difference.
5. **Read the scope word in the task sentence.** "The" statistic over "all" records is one
   number; a per-group table is not it, and a threshold computed per segment is not the
   threshold over the whole set.
6. **Two independent parameter ranges make a grid, not a diagonal**, unless the task pairs
   them explicitly.

## Presence

7. **A specific only some candidates state is a difference worth recording, not a defect of
   the others' and not a fabrication by default.** Check it against the source (`grep` the
   figure, the identifier, the clause). Confirmed, it is material a later phase can use
   whichever candidate is chosen; record who has it and where. The inventory tool
   (evidence-bundle) lists such specifics across all candidates at once.
