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

"""Paragraphs (with styles) and, optionally, tables of a .docx in reading order.

usage: docx_text.py FILE [--tables]

Paragraph lines:  [Style] text        Table dump (with --tables):
                                        ## table 3 (5 rows x 4 cols)
                                        cell<TAB>cell<TAB>...
"""

import argparse
import signal

import docx

signal.signal(signal.SIGPIPE, signal.SIG_DFL)
ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
ap.add_argument("file")
ap.add_argument(
    "--tables", action="store_true", help="also dump every table cell by cell"
)
a = ap.parse_args()

d = docx.Document(a.file)
print(
    f"# {a.file}: {len(d.paragraphs)} paragraphs, {len(d.tables)} tables, "
    f"{len(d.sections)} sections, {len(d.inline_shapes)} inline images"
)
for p in d.paragraphs:
  if p.text.strip():
    print(f"[{p.style.name}] {p.text}")
if a.tables:
  for i, t in enumerate(d.tables, 1):
    rows = t.rows
    ncols = max((len(r.cells) for r in rows), default=0)
    print(f"\n## table {i} ({len(rows)} rows x {ncols} cols)")
    for r in rows:
      print("\t".join(c.text.replace("\n", " ").strip() for c in r.cells))
