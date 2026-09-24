# Adjudication

You are deciding, not investigating. Two sessions examined the N candidates and neither saw the
other's work: `ledger_elim.json` holds the disagreements one of them worked and who came out
right; `ledger_fals.json` holds the positions all candidates share and whether each survived an
attempt to break it. You have neither session's context, and that is the point: only the two
records, spec/, workspace/ and the deliverables count. Read spec/ and both records first.

Both records are provisional. Check every entry you lean on: does what was checked actually
show what the entry says? Re-run a command when it matters. Weigh, do not count — one finding
on what the task asked for outweighs three on trivia. Prose is not evidence, a majority is not
evidence, and overturning either record needs a workspace or spec fact, not an argument.

You decide three things and write them to `finish.json`.

**The base.** The candidate the deliverable is built from: the one the evidence charges least
on what the task asked for. When the candidates still standing are separated by nothing you can
check, prefer the one that departs least from the input for the same result, and say so. The
base is `"none"` when no candidate's deliverable is worth starting from — nothing usable was
delivered, or the whole of it rests on a position that did not hold; the deliverable is then
built from the inputs.

**The work.** Everything the base must change to become the deliverable the evidence supports,
one entry each: an item another candidate got right and the base did not; something the spec
requires that nobody delivered and the workspace determines; a shared position that did not
hold, to be rebuilt from the inputs you name. Say what it should become, with the figure, and
which entry or check backs it. What the evidence does not back is not work. When the base is
none, the work is the whole deliverable, item by item, from the inputs.

**What is still open.** A fork neither record settles — two readings both defensible from
spec/ and workspace/ — does not disappear because you could not decide it. List it, with both
readings and what each yields. If one of them is the reading you would deliver were you allowed
only one, say which and why. The repair phase delivers both where the deliverable's form allows
it and falls back on your preference where it does not; it cannot deliver a reading it never
heard about. An open fork is not a defect in your work — recording it is the work.

    {"base": "<rollout name>" | "none",
     "work": [{"what": "<the item>", "to": "<what it should be, with the figure>",
               "evidence": "<the entry, or the check you ran>"}],
     "open": [{"item": "<the fork>",
               "readings": ["<reading and its figure>", "<reading and its figure>"],
               "prefer": "<the reading you would deliver alone, and why — or empty>"}],
     "notes": "<what decided the base, and anything the repair phase should know that fits nowhere above>"}
