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

"""Pre-rendered views: plain-text siblings of binary artifacts, so that one grep compares a

cell or a passage across every rollout and the task inputs.

    <name>.xlsx  -> <name>.xlsx.cells.tsv   one line per non-empty cell:
    Sheet!A1 <tab> value <tab> formula
    <name>.docx / .pptx / .pdf -> <name>.<ext>.text.txt   the document's text,
    tables row by row

Views belong to the harness, not to any rollout: they never count as delivered
files and
graders never see them (`is_view`).
"""

import os
from pathlib import Path

from harness.materialize.renderers import render_cells_tsv

VIEW_SUFFIXES = (".cells.tsv", ".text.txt")
TEXT_VIEW_CAP = 400_000  # characters per document


def is_view(name: str) -> bool:
  return name.endswith(VIEW_SUFFIXES)


def _docx_text(path) -> str:
  import docx

  doc = docx.Document(str(path))
  lines = []
  for block in doc.element.body.iterchildren():
    tag = block.tag.rsplit("}", 1)[-1]
    if tag == "p":
      para = docx.text.paragraph.Paragraph(block, doc)
      style = (para.style.name or "") if para.style is not None else ""
      text = para.text.strip()
      if text:
        lines.append(
            ("# " if style.startswith(("Heading", "Title")) else "") + text
        )
    elif tag == "tbl":
      for row in docx.table.Table(block, doc).rows:
        lines.append(
            " | ".join(c.text.strip().replace("\n", " ") for c in row.cells)
        )
  return "\n".join(lines)


def _pptx_text(path) -> str:
  from pptx import Presentation

  lines = []
  for i, slide in enumerate(Presentation(str(path)).slides, 1):
    lines.append(f"# slide {i}")
    for shape in slide.shapes:
      if shape.has_text_frame:
        lines += [
            p.text.strip()
            for p in shape.text_frame.paragraphs
            if p.text.strip()
        ]
      if getattr(shape, "has_table", False) and shape.has_table:
        lines += [
            " | ".join(c.text.strip() for c in row.cells)
            for row in shape.table.rows
        ]
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
      notes = slide.notes_slide.notes_text_frame.text.strip()
      if notes:
        lines.append(f"[notes] {notes}")
  return "\n".join(lines)


def _pdf_text(path) -> str:
  import fitz

  with fitz.open(str(path)) as doc:
    return "\n".join(
        f"# page {i}\n{page.get_text().strip()}"
        for i, page in enumerate(doc, 1)
    )


_TEXT_RENDERERS = {".docx": _docx_text, ".pptx": _pptx_text, ".pdf": _pdf_text}


def render_views(root: Path, refresh: bool = False) -> int:
  """Give every workbook and document under `root` its sibling view, where missing (or, with

  `refresh`, again: a pool materialized by an older renderer gets the current
  view).
  Shared stores behind symlinks are not entered. Unreadable files are skipped: a
  view is a
  convenience, and the file itself is still there to be opened. Returns the
  number written.
  """
  written = 0
  for dirpath, _dirs, files in os.walk(root, followlinks=False):
    for fn in sorted(files):
      p = Path(dirpath) / fn
      if p.is_symlink() or is_view(fn):
        continue
      ext = p.suffix.lower()
      if ext in (".xlsx", ".xlsm"):
        out = p.with_name(fn + ".cells.tsv")
        if (refresh or not out.exists()) and render_cells_tsv(p, out):
          written += 1
      elif ext in _TEXT_RENDERERS:
        out = p.with_name(fn + ".text.txt")
        if out.exists():
          continue
        try:
          text = _TEXT_RENDERERS[ext](p)
        except Exception:  # noqa: BLE001
          continue
        if text.strip():
          out.write_text(text[:TEXT_VIEW_CAP], encoding="utf-8")
          written += 1
  return written
