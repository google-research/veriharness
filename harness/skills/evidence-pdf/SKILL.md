---
name: evidence-pdf
description: Use when a claim you are checking turns on what a PDF actually shows — a number read off a chart, a table cell, a figure label, a page layout. Extracted text keeps neither the visual order nor the association between labels and values; extract tables with their columns, render the page to an image and look at it, or extract words with their coordinates.
---

# PDF evidence

Scripts (run with `python3`; paths are relative to this directory):

- `scripts/pdf_render.py FILE PAGE [--dpi 150] [--crop x0,y0,x1,y1]` — renders one
  page (1-based) to a PNG under /tmp/pdf_pages/ and prints its path. Open that
  path with the `read` tool: you will see the page as an image. `--crop` takes
  fractions of the page (e.g. `0,0.4,1,0.8`) to zoom into a chart.
- `scripts/pdf_words.py FILE PAGE [--grep REGEX]` — every word on the page with its
  coordinates, ordered top-to-bottom then left-to-right, so a label can be tied to
  the value that sits next to it by position rather than by text-stream order.
- `scripts/pdf_tables.py FILE PAGE [--all-pages] [--strategy lines|text]` — the
  tables on a page as tab-separated rows with their columns kept. Use this for any
  table; plain text extraction (pdftotext, text streams) flattens the layout and
  interleaves the columns of a multi-column table.
- Scanned pages: render first, then `tesseract /tmp/pdf_pages/<png> -`.

What the evidence means:

- Text-stream order is not visual order. Charts emit labels and values as separate
  runs; matching them by position in the text stream is guesswork. Look at the
  rendered page before concluding which bar belongs to which label.
- A table read as flat text is unreliable: a value that "sits under" a header in the
  stream may belong to another column. Read tables with pdf_tables.py, and when the
  detector finds none, from the rendered page.
- When rollouts disagree about a figure, the rendered page is the primary source.
  A rollout's own reading or OCR in its trajectory is testimony about the page,
  not the page.
- Page numbers in citations may be printed numbers, not PDF indices; confirm the
  page by looking at it.
