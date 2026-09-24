---
name: evidence-pptx
description: Use when a claim you are checking turns on what a PowerPoint deck (.pptx) actually contains — slide text, a table on a slide, a chart's series, speaker notes, the number and order of slides, or the layout. Walks every shape in slide order (tables cell by cell, groups, charts, notes) and marks what cannot be read as text, and renders slides to images for layout and pictures.
---

# Slide deck evidence

Scripts (run with `python3`; paths are relative to this directory):

- `scripts/pptx_text.py FILE [--slides 3,5-7] [--no-notes]` — every slide in order:
  title, each text frame, each table as tab-separated rows, chart type with categories
  and series values, speaker notes. Pictures, charts whose data cannot be read, and
  unreadable shapes are printed as such — a line like `[picture …]` or `[shape …:
  UNREADABLE]` means the slide holds content this pass did not capture.
- `scripts/pptx_render.py FILE [--dpi 110]` — one PNG per slide under
  /tmp/pptx_render/<name>/ for the `read` tool. Judge layout, pictures, embedded
  charts and anything the text pass marked unreadable from these.

What the evidence means:

- Ad-hoc readers miss content: text in tables, in grouped shapes and in placeholders is
  easy to skip, and shape iteration order is not always reading order. A count of
  slides, sections or bullets that "the deck lacks" must come from this walk plus the
  rendered slides, not from a first script's output.
- Numbers on a slide are claims, not data. Trace each one you rely on to its source in
  workspace/ before treating it as verified.
- A deliverable asked for as a deck is judged as a deck: slide count and order, one
  idea per slide, a title on each, tables that fit — check these on the rendered pages.
- Legacy `.ppt` files cannot be read this way; convert first
  (`soffice --headless --convert-to pptx FILE`) and note that you did.
