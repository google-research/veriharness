---
name: evidence-bundle
description: Use when the candidates each delivered a bundle of documents (reports, workbooks, decks, exports) and you need to see, across all of them at once, who delivered what - which files, which sections, and which specific figures, identifiers and dates appear in some candidates and not in others. One script prints that inventory from the pre-rendered text views in seconds; what to make of it is yours to decide.
applies-to: *.docx, *.pptx, *.pdf, *.csv, *.md, *.txt, *.html
---

# Who delivered what

Reading ten bundles one after another, differences of *value* stand out and differences of
*presence* do not: the finding only two candidates state, the table only one built, the
invoice number most of them never cite. Those are often what separates a complete deliverable
from a plausible one, and they cost nothing to see once the bundles are side by side.

- `python3 scripts/bundle_inventory.py rollouts [--base rNN] [--min-len 4] [--max 60]`
  reads every candidate's deliverables through their text views (`.text.txt`, `.cells.tsv`)
  and plain-text files, and prints: (1) the files each candidate delivered, with sizes; (2) the
  headings each candidate has that others lack; (3) the *specifics* - figures, identifiers,
  dates - grouped by how many candidates state them, each with the file and the line it sits
  in. With `--base rNN` it lists only what other candidates state and rNN does not.

What the inventory is and is not:

- It is a map, not a verdict. A specific that only one candidate states may be the insight the
  others missed or a fabrication; check it against `workspace/` (`grep` the figure, the name,
  the clause) before relying on it either way.
- A figure that *differs* between candidates shows up as two rarely-held specifics. That is a
  disagreement of value, to be settled from the inputs, not an omission.
- It sees text, not meaning: a candidate that states the same fact in words rather than digits
  will look as if it lacks it. Read the line in context before concluding anything.
