---
name: evidence-docx
description: Use when a claim you are checking turns on what a Word document (.docx) actually contains — its text and headings, the cells of its tables, tracked changes, comments, or embedded numbers. Reads the document in reading order with structure preserved, dumps tables cell by cell, and exposes revisions and comments that plain text extraction hides.
---

# Word document evidence

Scripts (run with `python3`; paths are relative to this directory):

- `scripts/docx_text.py FILE [--tables]` — paragraphs in reading order, each
  prefixed with its style (Heading 1, List Paragraph, …); with `--tables`, every
  table is dumped afterwards as rows of tab-separated cells, in document order.
  Text inside tables is not repeated in the paragraph stream, so a number that
  "isn't in the document" may be in a table.
- `scripts/docx_changes.py FILE` — tracked insertions and deletions (author,
  date, text) and comments (author, anchored text, comment text), read from the
  OOXML parts directly. A document with pending revisions reads differently
  depending on whether they are accepted; say which reading you used.
- Headers, footers, footnotes and text boxes are separate OOXML parts; if a
  figure could live there, unzip the .docx and grep `word/*.xml`.

What the evidence means:

- Structure is evidence. A deliverable that was asked for sections, a table, or
  a numbered list either has them or does not; check the styles and tables, not
  only the prose.
- Numbers in a document are claims, not data. Trace each one you rely on to its
  source in workspace/ before treating it as verified.
- Legacy `.doc` files cannot be read this way; convert first
  (`soffice --headless --convert-to docx FILE`) and note that you did.
