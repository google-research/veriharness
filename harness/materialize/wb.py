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

"""WorkBuddy adapter.

Workspace = the dataset task's `environment/` (the starting state the actor
worked on). `tests/`, `solution/` and `task.toml` are the benchmark's own
verifier material and never move. Deliverable = the run's agent.patch with
dependency/build-path file diffs dropped (inline count kept). Deliverables per
rollout: the RAW agent.patch (verbatim — no filtering; the verifier reads files
on demand and decides for itself what matters) plus, where the archive kept
them, the actual produced artifacts (`verifier/raw_artifacts/`, office domain
~91%). Nothing else under verifier/ moves — test_output, llm_judge, score,
reward are the benchmark's own grading of the rollout. Trajectory = ATIF steps
with tool results rejoined from the raw CLI stream.
"""

import json
import os
from pathlib import Path

from harness.materialize.base import DATA, Rollout, SRCROOT, Task
from harness.materialize.renderers import render_atif_steps, wb_tool_results

# Index of archived WorkBuddy run directories: {pool: {task: {seed: run_dir}}}.
INDEX = Path(
    os.environ.get("VERIHARNESS_WB_INDEX")
    or SRCROOT / "benchmarks/workbuddy/wb_index.json"
)
DATASETS = SRCROOT / "benchmarks/workbuddy/workbuddy-bench/datasets"
DS_NAME = {
    "code": "wb-bench-code-v1.0",
    "office": "wb-bench-office-v1.0",
    "web": "wb-bench-web-v1.0",
}
POOLS = {"flash": "flash", "opus": "opus"}
REPOS = (
    DATA / "_worlds" / "wb"
)  # /workspace of each task's env image, exported offline (minus .git etc.)
DOMAINS = ("code", "office", "web")


def _patch_text(patch: Path):
  return lambda: patch.read_text(errors="replace")


def _traj(tf: Path, run_dir: Path):
  return lambda: render_atif_steps(
      json.loads(tf.read_text()), wb_tool_results(run_dir)
  )


def iter_tasks(pool: str):
  index = json.loads(INDEX.read_text())
  for dom in DOMAINS:
    entries = index.get(f"{POOLS[pool]}/{dom}", {})
    for tname, seeds in sorted(entries.items()):
      task_dir = DATASETS / DS_NAME[dom] / "tasks" / tname
      instr = task_dir / "instruction.md"
      task = Task(
          key=f"{dom}__{tname}",
          spec=instr.read_text(errors="replace") if instr.exists() else tname,
      )
      env = task_dir / "environment"
      if env.is_dir():
        task.trees.append((env, ""))
      repo = REPOS / tname / "repo"
      if repo.is_dir():  # the starting repository the actor worked in
        task.links.append(("repo", repo))
      for sd, info in sorted(seeds.items()):
        if info.get("reward") is None:
          continue
        d = Path(info["dir"])
        if not d.is_dir():
          continue
        patch = d / "verifier" / "agent.patch"
        tf = d / "agent" / "trajectory.json"
        texts = [("agent.patch", _patch_text(patch))] if patch.exists() else []
        files = []
        ra = d / "verifier" / "raw_artifacts"
        if ra.is_dir():
          files = [
              (p, str(Path("artifacts") / p.relative_to(ra)))
              for p in sorted(ra.rglob("*"))
              if p.is_file()
          ]
        task.rollouts[sd] = Rollout(
            seed=sd,
            score=float(info["reward"]),
            texts=texts,
            files=files,
            traj=_traj(tf, d) if tf.exists() else None,
        )
      yield task
