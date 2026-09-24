# Copyright 2026 The VeriHarness Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""JobBench adapter.

Workspace = the task's own input folders (task_folder,
files_required_to_search). RUBRICS.json / eval_result live in the same task tree
and never move. Deliverables = the REAL delivered files archived under
results/output/main/<prof>/<tn>/model_output/<label>/ (full coverage both pools,
formula layers intact; the judge's extract cache was derived from exactly these
files, so the grading surface matches).
"""

import json
from pathlib import Path

from harness.materialize.base import Rollout, SRCROOT, Task
from harness.materialize.renderers import render_opencode_events

DS = SRCROOT / "benchmarks/jobbench/job-bench-eval/dataset/main"
JUDGE_ROOT = SRCROOT / "benchmarks/jobbench/results/judge/main"
TRAJ_ROOT = SRCROOT / "benchmarks/jobbench/results/traj/main"
OUTPUT_ROOT = SRCROOT / "benchmarks/jobbench/results/output/main"
JUDGE = "gemini-3-flash-preview"

POOLS = {
    "flash": (
        [f"gemini-3-5-flash-s{s:02d}" for s in range(1, 11)]
        + ["gemini-3-5-flash-lo30"]
    ),
    "opus": [f"opus48-s{s:02d}" for s in range(1, 11)],
}


def _pick_traj(tdir: Path) -> Path | None:
  """The archived deliverable comes from the SUCCESSFUL attempt; lanes retried

  on failure, so a label dir can hold several attempts. attempt_index.tsv
  records status per attempt: pick the last success, else the last attempt
  file (never the first, which is often the failed attempt).
  """
  jl = sorted(tdir.glob("*.jsonl")) if tdir.is_dir() else []
  if not jl:
    return None
  if len(jl) == 1:
    return jl[0]
  tsv = tdir / "attempt_index.tsv"
  if tsv.exists():
    rows = [
        l.split("\t") for l in tsv.read_text(errors="replace").splitlines()[1:]
    ]
    best = None
    for r in rows:
      if len(r) >= 11 and r[4] == "success":
        cand = tdir / Path(r[10]).name
        if cand.exists():
          best = cand
    if best is not None:
      return best
  return jl[-1]


def _render_traj(f: Path):
  return lambda: render_opencode_events(
      f.read_text(errors="replace").splitlines()
  )


def iter_tasks(pool: str):
  labels = POOLS[pool]
  for instr in sorted(DS.glob("*/task*/task_folder/TASK_INSTRUCTIONS.txt")):
    td = instr.parent.parent
    prof, tn = td.parent.name, td.name
    task = Task(key=f"{prof}__{tn}", spec=instr.read_text(errors="replace"))
    task.trees.append((td / "task_folder", "task_folder"))
    frs = td / "files_required_to_search"
    if frs.is_dir():
      task.trees.append((frs, "files_required_to_search"))
    for lbl in labels:
      jf = (
          JUDGE_ROOT
          / prof
          / tn
          / "eval_result"
          / f"eval_{lbl}"
          / f"{JUDGE}_judge.json"
      )
      if not jf.exists():
        continue
      try:
        jd = json.loads(jf.read_text())
      except Exception:  # noqa: BLE001
        continue
      ms = jd.get("max_score") or 0
      score = ((jd.get("total_score") or 0) / ms) if ms else 0.0
      mo = OUTPUT_ROOT / prof / tn / "model_output" / lbl
      files = (
          [
              (p, str(p.relative_to(mo)))
              for p in sorted(mo.rglob("*"))
              if p.is_file()
          ]
          if mo.is_dir()
          else []
      )
      tf = _pick_traj(TRAJ_ROOT / prof / tn / "model_traj" / lbl)
      task.rollouts[lbl] = Rollout(
          seed=lbl,
          score=score,
          files=files,
          traj=_render_traj(tf) if tf else None,
      )
    yield task
