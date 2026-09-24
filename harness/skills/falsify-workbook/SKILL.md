---
name: falsify-workbook
description: Where a pool of spreadsheet deliverables goes wrong together. Scope first (the labelled cell left blank, the unasked cell filled or fixed), then the arithmetic defects the workbook exposes by itself (scale, references, ranges, check rows). One check per entry, run against the input workbook and the task, never candidates against each other.
applies-to: *.xlsx, *.xlsm, *.xls
phase: fals
---

# Where workbooks are wrong

A delivered workbook is read cell by cell, on stored values. Two things must hold: the cells the
task should change hold the intended value, and every other cell is still what the input had. A
formula written differently is fine when its value matches. What is not fine is a target left blank, a blank filled that should have stayed
blank, a given cell altered, or a stored value that differs — even when every downstream total
is identical. Ten rollouts editing one template agree on most cells, so consistency is not
correctness; and where they split, the clever reading is wrong more often than the plain one.

## Scope: which cells belong filled, which belong untouched

1. **List what the task names, then check each across its whole range.** Every quantity, row,
   period and sheet in the instruction; find each row by label and confirm a value in every
   column of the stated range, not only the first. A named row blank end to end is invisible to
   a diff of the candidates because they all skipped it.
2. **A blank needs a witness to be filled; with a witness it must be.** Witnesses, all readable
   in the input: the row's own earlier columns hold the formula (ragged row); an adjacent
   same-kind row carries the same formula shape across those columns (a margin blank beside a
   filled margin); an opening-balance row seeded in its first column; a live single-cell
   reference elsewhere already points at the blank; an existing formula shows `#DIV/0!` or
   `#REF!` because it reads the blank; the blank sits at a labelled row under a headed column
   and is pre-formatted like its filled neighbours; a quarter or month block followed by a
   year/total column left empty (flow = SUM of the sub-periods, balance = last sub-period,
   ratio = the ratio of the totals, driver = blank). "The task named only the other rows",
   "blank is the original state" and "a sibling arrived pre-filled" are not reasons to leave a
   witnessed blank; a scope word ("for the forecast years") does not excuse a blank a present
   formula errors on.
3. **No witness, no fill.** A raw line item with no formula anywhere in its row, a first-period
   "change" with no prior period, the historical columns of a driver row whose forecast cells
   are typed-in assumptions, a per-entity subtotal or a grand total the block never had, a
   duplicated column, an explanatory note: a candidate that added these is charged, not
   credited for thoroughness. Completeness counts only on cells with a witness.
4. **"Complete the model" means the driven chain.** When the output line depends on rows that
   are themselves blank in the forecast columns, a pool that filled only the output built a
   formula reading empty cells as zero. Trace the feeders and name each row the region needs.
5. **When the task is to find and fix errors, the error class is the scope.** The instruction,
   the file name or a sheet title often names the class (a lookup, an average, double counting,
   a hardcode, anchoring, a sign, a unit). The intended fix is every instance of that class —
   sweep every sheet for it, siblings show the correct form — and nothing outside it. A latent
   oddity of another kind (an odd input value, a second broken reference, a label that looks
   wrong) is part of the intended original; a candidate that "also fixed" it is charged. Prefer
   the candidate complete in class and silent out of class over both the two-cell fix and the
   sixty-cell audit.

## Arithmetic the workbook exposes by itself

6. **Read the model's own check rows** for every period; a check that holds early and breaks
    later localises the year. A data table must reproduce its base case at the base inputs.
7. **Grep for error values and formulas with no cached value.** A dangling `#REF!` usually
    wants its deleted row back, not a patched reference.
8. **Scale.** Compare each per-unit metric with the sheet's own version of it (monthly vs
    annual per-unit, thousands vs units, percent stored as 1 vs 0.01); a projected formula
    carries the same unit conversion as the historical definition. A headline that is
    impossible for this model is a scale defect, not an opinion.
9. **Every reference lands on a populated cell whose label matches the referring line.** A
    rate range filled only in its first column applies zero afterwards; "Depreciation" must not
    land on "Capex". Scan each row across its columns: the odd formula out — shifted one
    column, relative where siblings are anchored — is the bug.
10. **An aggregate covers exactly its labelled block** — not the blank rows after it, not the
    subtotal, not skipping a member its sibling includes; a line inside two subtotals is
    double-counted. A growth row computes `current/previous − 1`. A hardcode inside a block of
    links has a findable source cell.
11. **Bold means header; not bold means fill it.** Compare `font.bold` against a known header
    and a known data row before treating a labelled row as a heading. Where the workbook
    applies a colour convention consistently, a cell breaking it is a real difference.

## Before you charge or hold

A shared position is not upheld by restating its arithmetic: confirm it with a cell filled in
the input or a downstream consumer, or record it broken with the exact cells and the formula a
correct deliverable writes. A defect present identically in the input is the target only when
the task is to audit and fix — and then only within the class it names (5).
