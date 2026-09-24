---
name: evidence-patch
description: Use when the candidates' deliverable is a code patch (agent.patch, *.diff) against a repository in workspace/. Builds one scratch tree per candidate, applies each patch, runs the project's own tests and one targeted reproduction of what the task asks in every tree, and records pass/fail per candidate as evidence. Says which execution results can be trusted and which are artefacts of this machine.
applies-to: *.patch, *.diff
---

# Code-patch evidence: run it, in every candidate, the same way

Reading ten diffs tells you what the authors intended. Running them tells you what
they do. Both sessions should run; a position about behaviour that was never executed
is recorded as unexecuted.

Script (run with `python3`; path relative to this directory):

- `scripts/patchlab.py build --base workspace/repo --out /tmp/lab r01=rollouts/r01/deliverables/agent.patch ...`
  makes `/tmp/lab/_base` (a real copy, symlinks resolved, committed in a throwaway
  git repo) and `/tmp/lab/rNN` = base + that candidate's patch. It drops cache /
  dependency / binary-stub sections, tries strict apply, then --recount, then
  --3way, then patch(1), and writes `build.json` (applied, mode, files, skipped,
  stderr). Ten candidates build in seconds.
- `scripts/patchlab.py run --out /tmp/lab [--timeout 300] [--jobs 4] [--tag T] -- CMD`
  runs the same shell command with cwd = each tree, `_base` included, in parallel,
  prints one line per tree and keeps the full output in `/tmp/lab/<name>.<T>.log`.

Procedure (budget: build <1 min, tests <5 min, reproduction <10 min for all ten):

1. Build all candidates. A patch that is empty, missing or does not apply is a
   finding about that candidate, recorded as such; an empty patch means "the
   repository as it was", which can be the right answer when the others break
   something.
2. Run the project's own tests in every tree AND in `_base`:
   `run -- PYTHONPATH=. python3 -m pytest -q -p no:randomly -p no:cacheprovider -o addopts= <tests dir>`.
   Compare each row with `_base`: only a test that passes in `_base` and fails in a
   candidate (or the reverse) is evidence. Failures `_base` shares are the machine's, not the candidate's.
   Tests a candidate added itself count for nothing on their own - every author's
   tests pass on their own patch.
3. Existing tests rarely separate candidates: they passed before the change. Write
   ONE reproduction script from the task's own sentence - the public call, command
   or input the requester would use, the example they gave, plus the two or three
   nearest variants and one "normal use must not change" case - that prints plain
   results and never asserts. Run it in every tree with `--tag repro` and group the
   trees by identical output (`md5sum /tmp/lab/*.repro.log`). Each group is a
   behaviour; `_base`'s group is "not fixed". Then decide which group the task's
   wording asks for. Probe the entry point the task names, not an internal helper
   you found in the diff.
4. Where the task adds an API whose spelling the task does not fix, probe the
   plausible call shapes in each tree and record which are accepted. A candidate
   accepting the project's existing idiom for that option is safer than one
   inventing a new keyword.
5. Record per candidate: applied?, tests vs base, reproduction group. Put the
   command lines in the ledger so the repair phase can rerun them.

What can mislead you here:

- `workspace/repo` may be a symlink into a read-only store. `cp -r workspace/repo X`
  copies the link, and every later write fails with "Read-only file system". Use
  the script, or `cp -rL`, or `cp -r workspace/repo/. X/`.
- The repository is not a git checkout. `git apply` outside a repo silently does
  less; `git init && git add -A && git commit` first (the script does).
- The machine's Python already has many libraries installed, sometimes the very
  project under test. `python3 script.py` puts the SCRIPT's directory on the path,
  not the tree: without `PYTHONPATH=.` (or `python3 -m` from the tree root) all ten
  candidates import the same installed copy and look identical. Check once with
  `python3 -c "import pkg; print(pkg.__file__)"` inside a tree.
- Never `pip install` (editable or not) a candidate: the interpreter is shared
  with other work, and an editable install redirects every later import to one tree.
- Plain `pytest` can stall for minutes or die with INTERNALERROR
  from an auto-loaded plugin. Always pass `-p no:randomly -p no:cacheprovider`; if
  it still misbehaves use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and add back only the
  plugins the project's conftest needs (`-p pytest_asyncio.plugin`, ...).
  Always give a timeout; never run the suite against the read-only workspace.
- The interpreter version here may differ from the one the project targets. A
  bug that exists only on another version cannot be reproduced; say so and fall
  back to reading, do not report "could not reproduce" as "not a bug".
- Some test suites write outside their tree (site-packages probes, $HOME). Run
  those with `--jobs 1`.
- No containers, no network installs. If a dependency is missing, test the part
  that imports without it and record the rest as unexecuted.

## When the patch builds a page

Build the trees as above, then look at the page the way its reader gets it: serve
ONLY the directory the task names as the output location (not the repository root)
over http and open it in a headless browser.

- `scripts/pageprobe.py TREE/<output dir> [--page index.html] [--mobile] [--click 12] [--out DIR]`
  serves the directory on a free local port, loads the page in headless Chromium
  and prints JSON: requests that failed or left the served root, console errors and
  uncaught exceptions, text length, counts of buttons / inputs / svg children /
  canvas, horizontal overflow, what changed when each visible control was clicked,
  and a screenshot path for the `read` tool. About 2-4 s per candidate.
- First question for every candidate: does it work from its own output directory? A
  page that fetches `../assets/data.json` or an absolute machine path draws an
  empty chart for the reader even though it worked where the author built it.
  Failed requests + an svg/canvas with no children + controls that change nothing
  is the signature.
- Then the task's own interactions, scripted once and run on every candidate:
  the control named in the brief exists, clicking it changes the DOM, state
  survives reload if persistence is asked, no overflow at 390 px if mobile is asked.
- Look at the screenshot: layout judged from the DOM alone misses overlap and blank areas.
- If the browser will not launch, do not download one; fall back to static checks
  (every src/href/fetch target resolves inside the output directory; `node --check`
  on each script; ids used in JS exist in the HTML) and record that the rendering
  was not executed.
- A visual judge is noisy: the same page can score differently twice. Do not edit a
  page that works to chase taste.
