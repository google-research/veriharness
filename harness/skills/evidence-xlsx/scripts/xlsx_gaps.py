#!/usr/bin/env python3
# Copyright 2026 The VeriHarness Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""xlsx_gaps.py WORKBOOK.xlsx

Structural incompleteness that the workbook itself evidences. Reads one file;
changes nothing;
lists, it does not decide. Four kinds of gap, each with its witness:

  RAGGED    a computed row whose formula stops before the period block ends
  DANGLING  a formula that reads an empty cell inside a populated row or column
  ERROR     a cell showing #DIV/0!, #REF!, #VALUE! or #N/A, and the empty cells
  it reads
  SIBLING   a labelled row left blank across columns where a same-block row of
  the same
            formula shape is filled

A gap is where to look, not proof that a cell must be filled: a row may be blank
by design.
The witness names what to check against the task and the sheet's own layout.
"""

from collections import defaultdict
import re
import sys

import openpyxl
from openpyxl.utils import get_column_letter

ERRORS = {"#DIV/0!", "#REF!", "#VALUE!", "#N/A", "#NAME?", "#NUM!"}
REF = re.compile(
    r"(?:'([^']+)'|([A-Za-z0-9_]+))?!?\$?([A-Z]{1,3})\$?(\d+)(?![\d(])"
)


def is_formula(v):
  return isinstance(v, str) and v.startswith("=")


def filled(v):
  return v is not None and not (isinstance(v, str) and not v.strip())


def label(ws, r):
  for c in range(1, min(ws.max_column, 4) + 1):
    v = ws.cell(r, c).value
    if isinstance(v, str) and v.strip() and not is_formula(v):
      return v.strip()[:40]
  return ""


def period_cols(ws):
  """Columns that hold values in most rows that hold any: the sheet's period band."""
  counts = defaultdict(int)
  rows = 0
  for row in ws.iter_rows():
    vals = [c for c in row if filled(c.value) and c.column > 1]
    if len(vals) >= 3:
      rows += 1
      for c in vals:
        counts[c.column] += 1
  return sorted(c for c, n in counts.items() if rows and n >= 0.5 * rows)


def shape(formula):
  """A formula with its cell references blanked: two rows of the same shape are siblings."""
  return re.sub(r"\$?[A-Z]{1,3}\$?\d+", "#", formula.upper())


def refs(formula, sheet):
  out = []
  for m in REF.finditer(formula):
    sh = m.group(1) or m.group(2) or sheet
    out.append((sh, f"{m.group(3)}{m.group(4)}"))
  return out


def main(path):
  wb_f = openpyxl.load_workbook(path, data_only=False)
  wb_v = openpyxl.load_workbook(path, data_only=True)
  found = 0
  for ws in wb_f.worksheets:
    wsv = wb_v[ws.title]
    band = period_cols(ws)
    if len(band) < 2:
      continue
    lines = []
    # RAGGED and SIBLING: per row, which band columns hold a formula
    rows = {}
    for r in range(1, ws.max_row + 1):
      cells = {c: ws.cell(r, c).value for c in band}
      forms = [c for c, v in cells.items() if is_formula(v)]
      empty = [c for c, v in cells.items() if not filled(v)]
      if forms:
        rows[r] = (forms, empty, shape(cells[forms[0]]))
        if empty and len(forms) >= 2:
          lines.append(
              f"  RAGGED   row {r} [{label(ws, r)}]: formula in"
              f" {get_column_letter(forms[0])}..{get_column_letter(forms[-1])},"
              f" empty {[get_column_letter(c) for c in empty]}"
          )
    for r in range(1, ws.max_row + 1):
      lbl = label(ws, r)
      if not lbl or r in rows:
        continue
      if all(not filled(ws.cell(r, c).value) for c in band):
        near = [
            q
            for q in (r - 2, r - 1, r + 1, r + 2)
            if q in rows and not rows[q][1]
        ]
        if near:
          q = near[0]
          lines.append(
              f"  SIBLING  row {r} [{lbl}] blank across"
              f" {get_column_letter(band[0])}..{get_column_letter(band[-1])};"
              f" row {q} [{label(ws, q)}] is filled with the same layout"
          )
    # DANGLING and ERROR
    for row in ws.iter_rows():
      for c in row:
        if not is_formula(c.value):
          continue
        for sh, coord in refs(c.value, ws.title):
          if sh not in wb_f.sheetnames:
            continue
          tgt = wb_f[sh][coord]
          if filled(tgt.value):
            continue
          trow = tgt.row
          if any(
              filled(wb_f[sh].cell(trow, k).value)
              for k in band
              if k != tgt.column
          ):
            lines.append(
                f"  DANGLING {ws.title}!{c.coordinate} reads empty {sh}!{coord}"
                f" (row {trow} [{label(wb_f[sh], trow)}] is otherwise"
                " populated)"
            )
        v = wsv[c.coordinate].value
        if isinstance(v, str) and v in ERRORS:
          empties = [
              f"{sh}!{k}"
              for sh, k in refs(c.value, ws.title)
              if sh in wb_f.sheetnames and not filled(wb_f[sh][k].value)
          ]
          lines.append(
              f"  ERROR    {ws.title}!{c.coordinate} shows {v}"
              + (f"; it reads empty {empties}" if empties else "")
          )
    if lines:
      found += len(lines)
      print(
          f"## {ws.title}  (period band"
          f" {get_column_letter(band[0])}..{get_column_letter(band[-1])})"
      )
      print("\n".join(dict.fromkeys(lines)))
  if not found:
    print("no structural gaps found")
  return 0


if __name__ == "__main__":
  if len(sys.argv) != 2:
    print(__doc__)
    sys.exit(1)
  sys.exit(main(sys.argv[1]))
