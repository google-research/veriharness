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
"""Words on a PDF page with coordinates, top-to-bottom then left-to-right.

usage: pdf_words.py FILE PAGE [--grep REGEX]

Prints:  y  x0  x1  text   (points; origin top-left). Words on the same line
share
y within a couple of points, so labels and the numbers beside them line up.
"""

import argparse
import re
import signal
import sys

import pdfplumber

signal.signal(signal.SIGPIPE, signal.SIG_DFL)
ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
ap.add_argument("file")
ap.add_argument("page", type=int)
ap.add_argument("--grep", help="regex; print only matching words")
a = ap.parse_args()
path, page_no = a.file, a.page
pat = re.compile(a.grep) if a.grep else None

with pdfplumber.open(path) as pdf:
  if not 1 <= page_no <= len(pdf.pages):
    sys.exit(f"page {page_no} out of range 1..{len(pdf.pages)}")
  page = pdf.pages[page_no - 1]
  words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
  words.sort(key=lambda w: (round(w["top"] / 3), w["x0"]))
  print(
      f"# page {page_no} of {len(pdf.pages)}  size"
      f" {page.width:.0f}x{page.height:.0f} pt  words {len(words)}"
  )
  for w in words:
    if pat and not pat.search(w["text"]):
      continue
    print(f"{w['top']:7.1f} {w['x0']:7.1f} {w['x1']:7.1f}  {w['text']}")
