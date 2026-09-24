# ledger_elim.json

One entry per disagreement you worked, including the ones you could not settle.

    {"disagreements": [
        {"question": "<what they answer differently — neutral: 'What is LBO!C33?', never 'Did r03 get C33 wrong?'>",
         "checked":  "<what you did to settle it: the command, the file and line, the spec clause — or 'nothing'>",
         "found":    "<what that showed, with the figures; and what each candidate actually commits to, by name>",
         "verdict":  "<who is right, by rollout name — or 'none of them' — or 'cannot tell', and why>"}
     ],
     "notes": "<which candidates you would keep and why, in a sentence — advice, not a verdict>"}

State the question neutrally and name the check behind every verdict. When nothing in the
materials can settle a question, `checked` is `"nothing"` and `verdict` is `"cannot tell"`
with both readings stated in `found` — that is a finding, not a failure. A difference that
changes no ranking is still an entry: which candidates have the thing and which do not.
