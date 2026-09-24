---
name: repair-xlsx
description: Use when a repair requires editing a workbook (.xlsx/.xlsm) in place — changing a formula or value, filling a blank row or period, flipping a sign, clearing an unasked fill — while keeping the file a valid, complete deliverable. Explains what an in-place edit breaks (cached values, dependents, charts), how to recalculate and prove the edit touched only what it should, and which edits not to make.
applies-to: *.xlsx, *.xlsm
phase: repair
---

# Editing a workbook without breaking it

A workbook edited with openpyxl is not finished when it is saved.

- **Cached values vanish.** openpyxl writes the formula and drops the cached value; every
  dependent is stale until something recalculates, and whoever opens the file reads cached values.
  Always recalculate after editing:
  `python3 scripts/xlsx_recalc.py out/deliverables/<file>.xlsx --baseline rollouts/<base>/deliverables/<file>.xlsx --inplace`
  It runs headless LibreOffice on a copy, prints every cell whose cached value changed versus
  the baseline (with its formula), reports formulas still without a value, and replaces the
  file (keeping a `.pre-recalc.xlsx` beside it).
- **Read that report.** The changed cells must be exactly the cells you edited plus their
  dependents. A change you did not intend means a formula you did not see references your
  cell — look at it before delivering, and revert if it is wrong.
- **Charts and formatting may not survive the round trip.** Run `xlsx_diff.py` base vs output
  and look at the formatting section, and at `xlsx_render.py` if the task involves charts. If
  LibreOffice damaged a chart or a number format that matters, deliver the `.pre-recalc.xlsx`
  version and say so in repair.json. Formatting differences by the thousand are LibreOffice's,
  not yours, and never a reason to revert a value you verified.
- **Circular models** (`xlsx_dump.py` reports iterative calculation on) may not converge under
  LibreOffice. If dependents drift across the whole model, keep the pre-recalc file and note it.
- **Verify like a verifier.** Recompute the corrected cells from the inputs yourself and
  compare with the recalculated values; that is the evidence line for repair.json.

## Edits that lose more than they win — decide before you edit

A reader holds the delivered workbook against the intended one: the cells the task targets must
match, and every other cell must still equal the input. So an edit is worth making only when the input
workbook or the task backs it, and three edits lose more than they win:

- **Fixing what the task did not ask about.** In a fix-the-errors task, the instruction, the
  file name or a sheet title usually names the error class. Fix every instance of that class
  and nothing else: a second broken reference, an odd-looking input, a "best practice" rewrite
  of a working formula are part of the intended original. Record them in repair.json; do not
  change them. If the base already fixes the whole class, the repair is no edit.
- **Filling a blank that has no witness.** Fill a blank when the row's own earlier columns hold
  the formula, an adjacent same-kind row carries it across those columns, a live formula reads
  the blank (or errors on it), or it is a year/total column after a filled quarter block.
  Do not add per-entity subtotals, grand totals, first-period changes with no prior period,
  historical back-fills of an assumption row, labels or notes that the block never had.
- **Applying an open fork's preference over a base that already stands.** When the work order
  is empty and the base satisfies both records, an open `prefer` that rests on an argument
  (not on a note, label or input-filled sibling) is recorded in repair.json, not written over a
  cell the base filled.

If the base changed a cell the input had filled and the task did not ask for it, restoring the
input's content is a repair the evidence always backs.

## Building what the pool left blank

- **Extend from the model's own precedent.** Fill the blank periods with the row's own formula,
  references shifted as Excel's fill-right would; never overwrite a populated cell. When the row
  is empty, mirror the adjacent sibling's formula, swapping only the operand the label names and
  keeping its offsets and `$` anchors. Fill the whole span the witness covers, not the first cell
  and not past the last column the sibling or consumer reaches.
- **When no period holds a formula**, write what the label and the driver rows present in those
  columns describe, using the same cells the model's other lines use.
- **Build the chain bottom up** — feeders first, then balances, then the change row, then the
  output — so no formula is left reading an empty cell. A year/total column: flows `SUM` the
  sub-periods, balances take the last, ratios divide the totals, drivers stay blank.
- Afterwards no formula in the region may reference an empty cell or show a new error value.

## Executing a settled convention

- **Prefer lifting to re-deriving.** When the work order names a rollout that already implements
  the reading, copy its exact cells for the named range — the line *and* the consumer cells
  whose operator or `*12`/`/12` factor moves with it — then recalculate.
- **A sign flip is two edits.** Negate the line and realign whatever consumes it (`−` ↔ `+`,
  or a mixed sum back to a plain `SUM`) so the consumer's value is unchanged while the stored
  sign changes. Apply across every period column.
- **A basis change moves once.** Annualize or de-annualize at the source line and remove the
  compensating factor at the consumer; totals must not move.
- **Open rows.** A cell the ledger left open is closed by the template's own convention — a
  note, the sibling cells' pattern, the sign of given inputs, the layout that ties out one way.
  If those are silent, the base's cell stands; a workbook never carries two values for one cell.
- **Dates and formats.** A number in a date-formatted cell prints as a date; check the number
  format before deciding the value is wrong. Give a cell you fill its row neighbours' format.

## Fixing planted errors: the whole pattern

One proven instance names a pattern (an AVERAGE range that skips a row, a hardcode where
siblings have formulas, a relative reference that should be absolute, a lookup keyed one
column off). Search every sheet for every cell that matches it — `xlsx_dump.py`, then the
sibling rows and columns — and fix them all in one pass; count instances before and after. A
pattern fixed in some cells and left in others compares as not fixed; a different pattern
fixed alongside it compares as a changed cell.
