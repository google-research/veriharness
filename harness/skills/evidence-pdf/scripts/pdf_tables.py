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

#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tables from a PDF page with their row/column structure kept (pdfplumber).

    python3 pdf_tables.py FILE PAGE [--all-pages] [--strategy lines|text]

Prints each table found on the page as tab-separated rows, one table per block.
Plain
text extraction (pdftotext, text streams) flattens the two-dimensional layout,
so a
multi-column table comes out interleaved; this keeps cells in their columns. If
no table
is detected, it says so — then render the page (pdf_render.py) and read it as an
image,
or use pdf_words.py to tie labels to values by coordinates.
"""

import argparse, signal

signal.signal(signal.SIGPIPE, signal.SIG_DFL)
import pdfplumber

ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
ap.add_argument("file")
ap.add_argument("page", type=int, nargs="?", default=1, help="1-based")
ap.add_argument("--all-pages", action="store_true")
ap.add_argument(
    "--strategy",
    choices=["lines", "text"],
    default="lines",
    help=(
        "lines: ruled tables (default); text: tables laid out by whitespace"
        " alone"
    ),
)
a = ap.parse_args()
settings = (
    {}
    if a.strategy == "lines"
    else {"vertical_strategy": "text", "horizontal_strategy": "text"}
)
with pdfplumber.open(a.file) as pdf:
  pages = range(1, len(pdf.pages) + 1) if a.all_pages else [a.page]
  found = 0
  for pn in pages:
    if pn < 1 or pn > len(pdf.pages):
      print(f"page {pn} out of range (1..{len(pdf.pages)})")
      continue
    tables = (
        pdf.pages[pn - 1].extract_tables(table_settings=settings)
        if settings
        else pdf.pages[pn - 1].extract_tables()
    )
    for ti, t in enumerate(tables, 1):
      found += 1
      print(
          f"# page {pn} table {ti}: {len(t)} rows x"
          f" {max((len(r) for r in t), default=0)} cols"
      )
      for row in t:
        print(
            "\t".join(
                "" if c is None else str(c).replace("\n", " ").strip()
                for c in row
            )
        )
      print()
  if not found:
    print(
        f"no table detected on page(s) {list(pages)} with"
        f" strategy={a.strategy}; try --strategy text, or render the page"
        " (pdf_render.py) and read it, or pdf_words.py for coordinates"
    )
