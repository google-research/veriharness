---
name: resolve-workbook
description: How to settle a split between spreadsheet candidates - what counts as deciding evidence when they store different formulas, signs or values in the same cell. The input workbook's own notes, labels and filled sibling cells decide; a majority and an argument from what the accounting "must" be do not.
applies-to: *.xlsx, *.xlsm, *.xls
phase: elim
---

# Settling a split between workbooks

A delivered workbook is read cell by cell, on stored values: two readings that produce the
same total but store different cells are different deliverables, not a tie. Locate the splits
mechanically (`xlsx_forks.py` in evidence-xlsx lists every cell the candidates store
differently, with the camps), then settle each from evidence in the input, in this order of
authority:

1. **A note or footnote cell in the input.** Search for one before ruling ("Note", "FN",
   "should", "must", "express", "basis", "uses"), and quote it. A method stated there is read
   literally.
2. **A label or header**: a leading minus on a label, a unit or period in a header, a
   section title, a subtotal label that spells its own arithmetic.
3. **A same-kind sibling formula filled in the input** - a parallel line of the same block
   that ships with its formula. It shows which cell a reference reaches, whether a period is
   converted, and how the first forecast column is treated. A cell the candidates filled is
   not a precedent, however many filled it alike.
4. **The task's words.**
5. **What most candidates did.**
6. **What the accounting or the industry "must" be.** An argument of this kind eliminates a
   camp only when nothing above speaks; when it would overturn the larger group or special-
   case one column of a dragged row, say so in the verdict rather than deciding on it.

Name the deciding cell in every verdict. When nothing in the workbook decides, record both
readings and what each yields; that is a finding, not a failure.
