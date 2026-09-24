---
name: repair-patch
description: Use in the repair phase when the base deliverable is a code patch. How to change a patch without breaking it - edit a tree, never the patch text - and the gate every delivered patch passes: applies cleanly to a pristine copy, reproduces the edited tree, passes everything the base passed, and differs in behaviour from the base only where the record asked for it.
applies-to: *.patch, *.diff
phase: repair
---

# Repairing a code patch

A patch that does not apply is worth nothing at all. The two usual ways a good base is
turned into nothing: a hunk header fixed up by hand, and a patch regenerated from a tree where the base's new files were already committed,
so "new file" sections became "modify" sections that a pristine repository rejects.

1. No authorised change -> copy the base's patch byte for byte. Stop.
2. Otherwise never edit patch text. `python3 <evidence-patch dir>/scripts/patchlab.py build --base workspace/repo --out /tmp/fix base=<base patch>`;
   edit files in `/tmp/fix/base`; then in that tree
   `git add -A && git diff --cached --binary HEAD > out/deliverables/agent.patch`
   (HEAD is the pristine commit the script made - the diff must be against
   pristine, not against the base candidate).
3. Gate, all four, or deliver the base's patch unchanged:
   a. `patchlab.py build --base workspace/repo --out /tmp/gate final=out/deliverables/agent.patch`
      reports `applied=True mode=strict`;
   b. `diff -r -x .git /tmp/fix/base /tmp/gate/final` is empty;
   c. the file list of the final patch = the base's list plus only files a change
      named; no caches, no scratch files, nothing the base had has vanished
      (compare `grep '^diff --git'` of both);
   d. the test command and the reproduction recorded by the investigation, run in
      `_base`, base-candidate and final: final passes everything the base candidate
      passed, and its reproduction output differs from the base candidate's only
      on the lines a recorded change was meant to move. Explain each differing line
      in repair.json; an unexplained difference is a regression - revert it.
4. What is not worth an edit: a feature, option, prefix, fallback or tolerance
   nobody asked for; turning an error into a silent skip (or the reverse) unless
   the task says so; renaming; reformatting; rewriting the base's tests. Every
   behaviour you add is a behaviour a hidden check may contradict; repairs that
   lose are additions of this kind; repairs that gain are one-line
   corrections to a message, a comparison, a constant, a required field.
5. For a patch that builds a page: rerun the page probe from the output directory
   on base and final; final must have no new failed requests / errors and every
   control that worked still works.
