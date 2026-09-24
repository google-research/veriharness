# ledger_fals.json

One entry per shared position you tried to break, including the ones you could not test.

    {"challenges": [
        {"claim":   "<the position every candidate holds, stated as they hold it>",
         "tried":   "<what you did to break it: the command you ran or the source you read — verbatim enough to re-run>",
         "found":   "<what it showed, quoted: the lines that carry the answer>",
         "holds":   true | false | "untested",
         "because": "<one or two sentences: why it holds — or what is wrong, what a correct deliverable does instead, and from which inputs>"}
     ],
     "notes": "<what you did not get to, and where a check would have gone>"}

`holds: false` is a strong claim: `found` must show the contradiction, and the task must have
asked for the thing that is wrong. Doubt is `"untested"`, with what would have settled it.
