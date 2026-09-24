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
"""Render one PDF page to PNG so it can be viewed with the read tool.

usage: pdf_render.py FILE PAGE [--dpi 150] [--crop x0,y0,x1,y1]

PAGE is 1-based. --crop takes fractions of the page width/height. Writes
/tmp/pdf_pages/<stem>_p<PAGE>[_crop].png and prints the path.
"""

import argparse
from pathlib import Path
import sys

import fitz  # PyMuPDF

ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
ap.add_argument("file")
ap.add_argument("page", type=int)
ap.add_argument("--dpi", type=int, default=150)
ap.add_argument("--crop", help="x0,y0,x1,y1 as fractions of the page")
a = ap.parse_args()
src, page_no, dpi, crop = Path(a.file), a.page, a.dpi, a.crop

doc = fitz.open(src)
if not 1 <= page_no <= doc.page_count:
  sys.exit(f"page {page_no} out of range 1..{doc.page_count}")
page = doc[page_no - 1]
clip = None
suffix = ""
if crop:
  x0, y0, x1, y1 = (float(v) for v in crop.split(","))
  r = page.rect
  clip = fitz.Rect(
      r.x0 + x0 * r.width,
      r.y0 + y0 * r.height,
      r.x0 + x1 * r.width,
      r.y0 + y1 * r.height,
  )
  suffix = "_crop"
out = Path("/tmp/pdf_pages")
out.mkdir(parents=True, exist_ok=True)
png = out / f"{src.stem}_p{page_no}{suffix}.png"
page.get_pixmap(dpi=dpi, clip=clip).save(png)
print(
    f"{png}  ({doc.page_count} pages in document; page label:"
    f" {page.get_label() or 'n/a'})"
)
