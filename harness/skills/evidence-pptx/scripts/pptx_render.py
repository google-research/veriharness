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

"""Render a .pptx to PNG pages (one per slide) for the `read` tool.

    python3 pptx_render.py FILE [--dpi 110]

Converts through headless LibreOffice to PDF, then rasterizes every page under
/tmp/pptx_render/<name>/slide-NN.png and prints the paths. Layout, pictures,
charts and
anything pptx_text.py marks as not readable are judged from these images.
"""

import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import fitz  # PyMuPDF

ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
ap.add_argument("file")
ap.add_argument("--dpi", type=int, default=110)
a = ap.parse_args()
src = Path(a.file).resolve()
out = Path("/tmp/pptx_render") / src.stem
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="pptx_render_", dir="/tmp") as td:
  copy = Path(td) / src.name
  shutil.copyfile(src, copy)
  r = subprocess.run(
      [
          "soffice",
          "--headless",
          "--convert-to",
          "pdf",
          "--outdir",
          td,
          str(copy),
      ],
      capture_output=True,
      text=True,
      timeout=300,
      env=dict(os.environ, HOME=td),
  )
  pdf = Path(td) / (src.stem + ".pdf")
  if not pdf.exists():
    print("conversion failed:", (r.stderr or r.stdout)[-300:])
    sys.exit(1)
  doc = fitz.open(pdf)
  for i, page in enumerate(doc, 1):
    p = out / f"slide-{i:02d}.png"
    page.get_pixmap(dpi=a.dpi).save(p)
    print(p)
print(f"# {len(doc)} slides rendered")
