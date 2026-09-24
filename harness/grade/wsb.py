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

"""Workspace-Bench Lite: the official agent-as-a-judge run inside the workspace-bench docker

image on a staged task dir {metadata.json, output/}. Score = passed rubrics /
n_rubrics, as in
materialize/wsb.py. Our deliverables dir mirrors the agent's output folder.
`_misplaced_outputs/`
IS part of that surface: it sits inside the benchmark's own output/ tree, so the
archived judge
saw it and we must too.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from harness.config import bench_root
from harness.views import is_view

WSB = bench_root() / "benchmarks" / "wsb_lite" / "official" / "evaluation"
TASKS = WSB / "tasks"
MODEL = (  # the judge model configured in the benchmark's runs/judge.yaml
    "claude-opus-4-8"
)
GRADER = "wsb/agent_as_a_judge"


def preflight() -> str:
  """See jb.preflight: the judge fails soft.

  When its litellm proxy is down every call burns the six-retry budget (about
  forty minutes a task) and then writes every rubric failed, so the cell scores
  0.000 and merely looks disappointing.
  """
  import json as _json
  import urllib.request

  env = {}
  for line in (WSB / ".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
      k, _, v = line.partition("=")
      env[k.strip()] = v.strip()
  url = env.get("JUDGE_BASE_URL", "")
  body = _json.dumps({
      "model": MODEL,
      "max_tokens": 1,
      "messages": [{"role": "user", "content": "ok"}],
  }).encode()
  req = urllib.request.Request(
      url.rstrip("/") + "/v1/chat/completions",
      data=body,
      headers={
          "Content-Type": "application/json",
          "Authorization": "Bearer " + env.get("JUDGE_API_KEY", ""),
      },
  )
  try:
    with urllib.request.urlopen(req, timeout=60) as r:
      _json.loads(r.read())
    return ""
  except Exception as e:  # noqa: BLE001
    return (
        f"wsb judge {MODEL} unreachable at {url}: {type(e).__name__}:"
        f" {str(e)[:200]}"
    )


def _stage(
    td: Path,
    key: str,
    deliverables: Path,
    meta: dict,
    trace: Path | None = None,
) -> None:
  (td / "output").mkdir(parents=True)
  # The judge reads agent.json for a filtered execution trace; archived rollouts were judged
  # with theirs. A rollout's bundle has it beside its trajectory; a delivered bundle (out/) is
  # judged with the base rollout's, which the scorer passes via `trace`.
  trace = trace or deliverables.parent / "trajectory" / "agent.json"
  if trace.is_file():
    shutil.copy2(trace, td / "agent.json")
  meta = {
      **meta,
      "__metadata_path": (
          f"/workspace/Workspace-Bench/evaluation/tasks/{key}/metadata.json"
      ),
  }
  (td / "metadata.json").write_text(
      json.dumps(meta, ensure_ascii=False, indent=1)
  )
  for p in deliverables.iterdir():
    if is_view(
        p.name
    ):  # our own pre-rendered view, never part of the deliverable
      continue
    (shutil.copytree if p.is_dir() else shutil.copy2)(p, td / "output" / p.name)


def _parse(td: Path, meta: dict, tail: str) -> dict:
  rj = td / f"rubrics_judge--{MODEL}.json"
  if not rj.exists():
    return {
        "score": None,
        "error": tail or "judge produced no rubric file",
        "grader": GRADER,
    }
  res = json.loads(rj.read_text())
  items = res.get("rubrics") or res.get("results") or res
  if isinstance(items, dict):
    items = items.get("rubrics") or []
  n = len(meta.get("rubrics") or [])
  passed = sum(1 for x in items if isinstance(x, dict) and x.get("passed"))
  return {
      "score": passed / n if n else 0.0,
      "detail": {"passed": passed, "n_rubrics": n},
      "rubrics": items,
      "grader": GRADER,
  }


def grade(
    key: str,
    deliverables: Path,
    timeout: int = 2400,
    trace: Path | None = None,
    **_,
) -> dict:
  meta_src = TASKS / key / "metadata.json"
  if not meta_src.exists():
    return {
        "score": None,
        "error": f"no tasks/{key}/metadata.json",
        "grader": GRADER,
    }
  meta = json.loads(meta_src.read_text())
  stage_root = Path(tempfile.mkdtemp(prefix="vh_wsb_", dir="/var/tmp"))
  try:
    os.chmod(stage_root, 0o777)
    _stage(stage_root / key, key, deliverables, meta, trace)
    subprocess.run(["chmod", "-R", "a+rwX", str(stage_root)], check=False)
    # As the host user, so the judge's outputs in the staging dir stay ours to read and remove.
    cmd = [
        "docker",
        "compose",
        "-f",
        "docker/docker-compose.yaml",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp/home",
        "-v",
        f"{stage_root}:/workspace/vh_stage",
        "workspace-bench",
        "python3",
        "-u",
        "/workspace/Workspace-Bench/evaluation/src/agent_as_a_judge.py",
        "--task-dir",
        "/workspace/vh_stage",
        "--eval-yaml",
        "/workspace/Workspace-Bench/evaluation/runs/judge.yaml",
        "--overwrite",
        "--workers",
        "1",
    ]
    try:
      p = subprocess.run(
          cmd, capture_output=True, text=True, timeout=timeout, cwd=str(WSB)
      )
      tail = (p.stderr or p.stdout)[-800:]
    except subprocess.TimeoutExpired:
      tail = "judge container timed out"
    return _parse(stage_root / key, meta, tail)
  finally:
    shutil.rmtree(stage_root, ignore_errors=True)
