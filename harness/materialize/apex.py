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

"""APEX adapter.

HF mercor/apex-agents supplies the prompt ONLY (the same record carries the
grading rubrics, which never move); digest caches supply the submitted answers;
results/examples supply trajectories and archived scores. `grades.json` /
`verifiers.json` in the run dirs are the answer key.

APEX has no file workspace: the actor operated in interactive app environments
(worlds) that no longer exist. What survives of the environment is (a) the
actor's initial context — initial_messages.json, the system+task messages it
started from (leak-checked: no rubric content) — written to
workspace/initial_messages.md once per task, and (b) the trajectories, which
carry every observation the actors made of the live world.
"""

from functools import lru_cache
import json
from pathlib import Path

from harness.materialize.base import DATA, Rollout, SRCROOT, Task
from harness.materialize.renderers import render_openai_messages

APEX = SRCROOT / "benchmarks/apex"
# pool -> (glob of the answer-digest cache under apex/dissolve/, seed-name prefix)
POOLS = {
    "flash": ("digest_cache_*_flash", "flash_high_s"),
    "opus": ("digest_cache_*_opus_high", "opus_high_s"),
}
DOMAIN = {
    "Investment Banking": "IB",
    "Management Consulting": "MC",
    "Law": "Law",
}


@lru_cache(maxsize=1)
def _tasks() -> list:
  from huggingface_hub import hf_hub_download

  p = hf_hub_download(
      "mercor/apex-agents", "tasks_and_rubrics.json", repo_type="dataset"
  )
  return json.loads(Path(p).read_text())


def _score(grades_file: Path) -> float:
  try:
    vr = json.loads(grades_file.read_text()).get("verifier_results") or []
  except Exception:  # noqa: BLE001 — an unreadable grade counts as zero, as in the archived scores
    return 0.0
  return sum(v.get("score", 0.0) for v in vr) / len(vr) if vr else 0.0


def _initial_context(run_dir: Path) -> str | None:
  f = run_dir / "initial_messages.json"
  if not f.exists():
    return None
  try:
    msgs = json.loads(f.read_text())
  except Exception:  # noqa: BLE001
    return None
  out = []
  for m in msgs:
    out.append(f"## {m.get('role', '?')}\n\n{m.get('content', '')}")
  return (
      "# The actor's initial context (from initial_messages.json)\n\n"
      + "\n\n".join(out)
  )


def _render_traj(run_dir: Path):
  def f():
    msgs = (
        json.loads((run_dir / "trajectory.json").read_text()).get("messages")
        or []
    )
    return render_openai_messages(msgs)

  return f


WORLDS = (
    DATA / "_worlds" / "apex"
)  # extracted world zips, one dir per zip hash; index.json maps task idx -> dir


def _world_dir(idx: int):
  try:
    stem = json.loads((WORLDS / "index.json").read_text())["idx2zip"].get(
        str(idx)
    )
  except (OSError, json.JSONDecodeError):
    return None
  return WORLDS / stem if stem and (WORLDS / stem).is_dir() else None


def iter_tasks(pool: str):
  cache_glob, prefix = POOLS[pool]
  cache = next(iter(sorted((APEX / "dissolve").glob(cache_glob))))
  ex = APEX / "results/examples"
  seeds = [f"{prefix}{s:02d}" for s in range(1, 11)]
  runs: dict[int, dict[str, Path]] = {}
  for seed in seeds:
    for gf in (ex / seed / "output").glob("idx*/grades.json"):
      idx = int(gf.parent.name.split("_")[0][3:])
      runs.setdefault(idx, {})[seed] = gf.parent
  for i, t in enumerate(_tasks()):
    cf = cache / f"{t['task_id']}.json"
    if not cf.exists():
      continue
    digests = json.loads(cf.read_text())
    task = Task(key=f"{i:03d}_{DOMAIN[t['domain']]}", spec=t["prompt"])
    wd = _world_dir(i)
    if (
        wd is not None
    ):  # the actor's starting world: filesystem/ (documents) and .apps_data/ (mail, calendar, chat)
      task.links.append(("world", wd))
    for rd in (runs.get(i) or {}).values():
      ctx = _initial_context(rd)
      if ctx:
        task.workspace_texts.append(("initial_messages.md", ctx))
        break
    for seed in seeds:
      answer = ((digests.get(seed) or {}).get("answer") or "").strip()
      if not answer:
        continue
      d = runs.get(i, {}).get(seed)
      task.rollouts[seed] = Rollout(
          seed=seed,
          score=_score(d / "grades.json") if d else 0.0,
          texts=[("answer.md", answer)],
          traj=_render_traj(d) if d is not None else None,
      )
    yield task
