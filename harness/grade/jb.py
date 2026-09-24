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

"""JobBench: the benchmark's own text judge (job-bench-eval/eval/judge.py) run on an arbitrary deliverable

directory against the task's RUBRICS.json, through an OpenAI-compatible judge
endpoint. Score =
total_score / max_score, as in materialize/jb.py. The judge is stochastic;
expect about one rubric
of run-to-run noise.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from harness.config import bench_root
from harness.views import VIEW_SUFFIXES

JB = bench_root() / "benchmarks" / "jobbench" / "job-bench-eval"
JUDGE = JB / "eval" / "judge.py"
DS = JB / "dataset" / "main"
# The judge is reached through an OpenAI-compatible endpoint (e.g. a local litellm proxy).
ENV = dict(
    JUDGE_MODEL=os.environ.get("JB_JUDGE_MODEL", "gemini-3-flash-preview"),
    JUDGE_API_BASE=os.environ.get(
        "JB_JUDGE_API_BASE", "http://127.0.0.1:4000/v1"
    ),
    JUDGE_API_KEY=os.environ.get("JB_JUDGE_API_KEY", ""),
)


def preflight() -> str:
  """A dead judge scores every rubric 0.0 and reports no error, so a whole cell comes out at

  0.000 and reads as a bad run. Liveliness is not enough: a proxy can answer its
  health
  check with zero registered deployments. Ask the judge model itself for one
  token.
  """
  import urllib.request

  body = json.dumps({
      "model": ENV["JUDGE_MODEL"],
      "max_tokens": 1,
      "messages": [{"role": "user", "content": "ok"}],
  }).encode()
  req = urllib.request.Request(
      ENV["JUDGE_API_BASE"].rstrip("/") + "/chat/completions",
      data=body,
      headers={
          "Content-Type": "application/json",
          "Authorization": "Bearer " + ENV["JUDGE_API_KEY"],
      },
  )
  try:
    with urllib.request.urlopen(req, timeout=60) as r:
      json.loads(r.read())
    return ""
  except Exception as e:  # noqa: BLE001
    return (
        f"jb judge {ENV['JUDGE_MODEL']} unreachable at {ENV['JUDGE_API_BASE']}:"
        f" {type(e).__name__}: {str(e)[:200]}"
    )


def grade(key: str, deliverables: Path, workers: int = 6, **_) -> dict:
  prof, tn = key.split("__", 1)
  rub = DS / prof / tn / "task_folder" / "RUBRICS.json"
  if not rub.exists():
    rub = next((DS / prof / tn).rglob("RUBRICS.json"), None)
  if rub is None or not rub.exists():
    return {
        "score": 0.0,
        "error": f"no RUBRICS.json for {key}",
        "grader": "jb/judge.py",
    }
  with tempfile.TemporaryDirectory(prefix="vh_jb_", dir="/var/tmp") as td:
    details = Path(td) / "details.json"
    # The judge inlines every file it finds, so stage a copy without our own pre-rendered
    # views: they are the harness's instrument, not part of the deliverable.
    staged = Path(td) / "output"
    shutil.copytree(
        deliverables,
        staged,
        ignore=shutil.ignore_patterns(*(f"*{s}" for s in VIEW_SUFFIXES)),
        symlinks=True,
    )
    cmd = [
        sys.executable,
        str(JUDGE),
        "--output-dir",
        str(staged.resolve()),
        "--rubrics-file",
        str(rub),
        "--details-file",
        str(details),
        "--judge-model",
        ENV["JUDGE_MODEL"],
        "--api-base",
        ENV["JUDGE_API_BASE"],
        "--api-key",
        ENV["JUDGE_API_KEY"],
        "--max-workers",
        str(workers),
        "--evaluated-model",
        "veriharness",
    ]
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,
        cwd=str(JB),
        env={**os.environ, **ENV},
    )
    if not details.exists():
      return {
          "score": 0.0,
          "error": (p.stderr or p.stdout)[-800:],
          "grader": "jb/judge.py",
      }
    d = json.loads(details.read_text())
  ms = d.get("max_score") or 0
  return {
      "score": (float(d.get("total_score") or 0) / ms) if ms else 0.0,
      "detail": {k: v for k, v in d.items() if k != "rubrics"},
      "rubrics": d.get("rubrics"),
      "grader": "jb/judge.py",
  }
