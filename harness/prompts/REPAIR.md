# Repair

`finish.json` is your work order: a base, the work, and what is open. The other candidates are
no longer competitors — they are the parts bin.

**Start from the base.** Copy the base's `deliverables/` into `out/deliverables/`, file for
file — same relative paths, names and formats, at the top of `out/deliverables/`, not nested.
Do this before anything else, and even if you then change nothing: a bundle that loses a file
scores as if that file were never produced. You may add files; never drop, rename or convert
one. Then edit the real files in place — openpyxl, python-docx, json; the repair skills cover
the formats. A note saying what should change is not a repair. When the base is `none`, build
the deliverable the spec asks for, under the names and formats it names, from the inputs.

**Do the work.** One entry at a time. Before each change, look at the evidence it rests on
yourself — the record entry, the candidate's file, the input cell — and if it does not hold,
skip the entry and say so. Bring content in adapted to the base's structure; where a figure is
to be rebuilt, compute it from the inputs named, never carry it over from a candidate. Do
nothing the work order does not authorize: nothing the spec did not ask for, no figure you
cannot trace to an input or an entry, no restyling. When the workspace does not determine a
value, leave the omission — a placeholder or an invented value is worse.

**Deliver the open forks.** First try to settle each: name the check that would, and run it
if the workspace lets you. Settled, it is work like any other. Unsettled, it depends on the
form of the deliverable. Where the form has room — a prose answer, a document with sections —
deliver both readings: the base's as the primary, the other in its own clearly labelled section
carried through to its own figures, not described in the abstract. Where the form has room for
one value only — a cell, a required field, a code patch — deliver the adjudication's preference
if it gave one; otherwise the base's reading stands and the other goes in `repair.json`, not
into the file.

**Check.** Every base file present under the same name and non-empty; every change recomputed
or diffed against its source, and the result opened the way a reader would open it; everything
else unchanged value for value — editing one cell with a library can silently rewrite others.
An edit that fails a check is reverted. If nothing was authorized, deliver the base unchanged
and say so.

Write `repair.json` in the task root, beside `finish.json`:

    {"base": "<rollout name>" | "none",
     "applied": true | false,
     "changes": [{"file": "<path under out/deliverables>", "what": "<one line>",
                  "evidence": "<the entry, or the check you ran>"}],
     "open": [{"item": "<the fork>", "delivered": "both | base | preferred"}],
     "summary": "<one or two sentences: what changed, what you verified, what you left alone and why>"}
