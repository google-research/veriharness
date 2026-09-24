---
name: repair-bundle
description: Use in the repair phase when the base deliverable is a set of office files — documents, spreadsheets, presentations, forms, exports — produced from source documents and a brief. How such a bundle is graded, how to take the coverage inventory against the other candidates at checklist granularity, how to bring a missing item into the base's own files, and what is never worth an edit.
applies-to: *.docx, *.pptx, *.pdf, *.csv, *.html, *.txt, output.md
phase: repair
---

# Repairing a bundle of office files

A bundle is graded as a checklist of specific content: the form filled with these
values, the memo naming this source, the ledger carrying this entry, the report
stating this finding with this figure. Each line is a conjunction of specifics — the
right amount, the right reference, the right date — and a general statement that
covers the topic without the specifics does not meet it. Missing items are the usual
cost; polish never pays.

## The coverage inventory

1. List what the brief asks for, one entry per verb and noun (each file, each
   section, each field, each named source, each computation).
2. See every candidate's content side by side: `bundle_inventory.py rollouts --base <base>`
   (evidence-bundle) lists in seconds the files, headings and specifics — figures,
   identifiers, dates — that other candidates state and the base does not, each with its
   file and line; the `.text.txt` / `.cells.tsv` views beside every document make any of
   them one `grep` away. A brief underdetermines what its reader will look for: a base that
   covers every clause in general terms routinely lacks the specific another candidate states.
3. For every candidate — a charge on one item does not taint the rest of what a
   candidate delivers, only the charged item — list what it has that the base
   lacks, at the granularity of the checklist: a section, a table row, a filled
   field, a cited source, a named finding, a specific value or reference, a file the
   brief asked for.
4. Sort the list. Items the sources confirm (`grep` the value, the name, the clause in
   `workspace/`): adopt, whether one candidate has them or nine.
   Items the sources give directly that no candidate has (an amount in the invoice,
   a clause in the manual): supply from the source. Items that state a
   different value for something the base or another candidate states are conflicts:
   settle them from the sources, or treat them as an open row. Items that trace to
   nothing in the workspace: leave out.
5. Then read the brief once more, clause by clause, against the base alone, and for
   each clause quote the base's text that satisfies it. A clause the base meets only
   in general terms — "the invoice was overpaid" — gets its specifics from the sources
   — check number, amount, date — when they are there; a clause the base does not
   meet at all is an obligation (kind 3), supplied from the sources when they
   determine it.

## Settling an open row

An open row is settled by the most authoritative file in the workspace, not the
nearest one: the standard or manual the brief names, the database or ledger the
figures come from, the letter or contract that sets a date — before a candidate's
header, a CSV label or a summary sheet. When the answer is a computation the
workspace makes possible (days between two dated documents, a total over a column,
a rate applied to a balance), run it and record the number. "The workspace cannot
settle it" is a claim made only after the authoritative file has been read.

## Bringing content in

Edit the base's own files: a paragraph or table row added where the base's structure
places it (python-docx, openpyxl, csv), in the base's terms and units, with the
sources' values. Keep the item's identifiers, amounts, dates and source names; a
paraphrase that loses them does not meet the line it was brought in for. A file the brief asks for that the base lacks and another candidate
has is added after its content is checked line by line against the sources; a file
nobody produced is written from the sources when the brief specifies its content. A
form or template the brief provides stays the base of its deliverable — content is
added into it, not into a fresh document.

## Never

Do not paste another candidate's document, or a digest of all candidates, after the
base's text. Do not restyle, reformat, rename, or add files the brief did not ask for.
Do not change a conclusion the base reached unless a decided row charges it. Do not
fill a field the brief left for someone else. Every formula cell in a delivered
workbook must carry a calculated value, whether or not you edited the workbook: a reader who
opens the file without recalculating it sees an uncalculated formula as an empty cell.
Recalculate (repair-xlsx) and re-extract every file you touched to confirm the added content reads
back and nothing else moved.
