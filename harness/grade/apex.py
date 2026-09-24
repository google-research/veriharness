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

"""APEX: the benchmark's own grading runner (benchmarks/apex/grading, `python -m runner.main`) run on a NEW

answer.md. Per-criterion LLM judge (output_llm eval,
gemini/gemini-3-flash-preview via litellm, AI Studio key)
with the task's own rubric from HF mercor/apex-agents; score = mean of
verifier_results[].score, as in
materialize/apex.py. The judge is stochastic (reasoning_effort=low); expect
occasional flips on borderline
criteria.

What is synthesized (the runner wants a full agent run; a repaired answer.md is
not one):
  * trajectory.json  -- AgentTrajectoryOutput with exactly two messages: user =
  the HF task prompt (the runner's
    extract_task_prompt reads the first user message; archived trajectories
    start with the same text), assistant =
    answer.md verbatim (final_answer helper returns messages[-1].content).
    status=completed, time_elapsed=0.
  * initial snapshot -- the task's world zip when the world index knows it (as
  archived), else empty;
    final snapshot -- the bundle minus answer.md. verifier_values built by the
    benchmark's own dissolve driver carry
    only {criteria, is_primary_objective}, so the initial snapshot is never
    opened for reference artifacts and the
    snapshot diff (which is what the judge sees as "artifacts") is empty by
    construction.
  * verifiers.json   -- one ec_output_llm verifier per rubric criterion,
  identical to main_dissolve.py.
  * grading_settings / eval_configs / scoring_config -- the benchmark's configs,
  referenced in place.

Artifact-based criteria (tasks whose expected_output is
make_new_doc/sheet/slide_deck or edit_existing_*,
58 of 480): with both snapshots empty such answers would be judged on the
message text alone
and fail whenever the answer lives in a file. The final snapshot therefore
carries the bundle's non-answer.md files,
so the judge sees them as created artifacts. Message-only bundles produce an
empty final zip, so the 422/480
message_in_console tasks are unaffected.
"""

from functools import lru_cache
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from harness import config
from harness.config import DATA, bench_root
from harness.views import is_view

# The benchmark's grading runner, installed by setup_benchmarks.sh (its upstream repository rewrites its
# history, so the exact version is not pinned; the interface used here was checked against upstream on
# 2026-09-22). The grading configuration is ours (harness/benchmarks/apex): the rubric judge with the
# settings the archived scores were produced with.
GRADING = Path(
    os.environ.get("APEX_GRADING_DIR")
    or bench_root() / "benchmarks" / "apex" / "grading"
).resolve()
PY = GRADING / ".venv" / "bin" / "python"
CONFIGS = config.HARNESS_DIR / "benchmarks" / "apex"
DOMAIN = {
    "Investment Banking": "IB",
    "Management Consulting": "MC",
    "Law": "Law",
}
GRADER = "apex/runner.main"
_KEY_RR = itertools.count(os.getpid())  # rotate judge API keys across calls


@lru_cache(maxsize=1)
def _tasks() -> list:
  from huggingface_hub import hf_hub_download

  try:
    p = hf_hub_download(
        "mercor/apex-agents",
        "tasks_and_rubrics.json",
        repo_type="dataset",
        local_files_only=True,
    )
  except Exception:  # noqa: BLE001 — cache miss: fetch
    p = hf_hub_download(
        "mercor/apex-agents", "tasks_and_rubrics.json", repo_type="dataset"
    )
  return json.loads(Path(p).read_text())


def _api_keys() -> list[str]:
  """The judge's API key(s): GEMINI_API_KEY, optionally several separated by commas,

  which are then rotated across calls to spread the per-key rate limit. Empty
  when the
  judge is reached through Vertex AI instead (APEX_JUDGE_MODEL=vertex_ai/...,
  with
  application-default credentials and VERTEXAI_PROJECT / VERTEXAI_LOCATION set).
  """
  return [
      k.strip()
      for k in os.environ.get("GEMINI_API_KEY", "").split(",")
      if k.strip()
  ]


def _grading_settings() -> Path:
  """The benchmark's grading settings, with the judge model swapped for APEX_JUDGE_MODEL

  when that is set (the benchmark's default is a litellm `gemini/...` model,
  which needs
  an API key; `vertex_ai/<same model>` needs only cloud credentials).
  """
  default = CONFIGS / "grading_settings.json"
  model = os.environ.get("APEX_JUDGE_MODEL")
  if not model:
    return default
  settings = {**json.loads(default.read_text()), "llm_judge_model": model}
  out = (
      Path(tempfile.gettempdir())
      / f"vh_apex_grading_settings_{os.getuid()}.json"
  )
  out.write_text(json.dumps(settings, indent=2))
  return out


def preflight() -> str:
  if not _api_keys() and not os.environ.get("APEX_JUDGE_MODEL", "").startswith(
      "vertex_ai/"
  ):
    return (
        "the APEX rubric judge needs GEMINI_API_KEY, or"
        " APEX_JUDGE_MODEL=vertex_ai/<model> with VERTEXAI_PROJECT and"
        " VERTEXAI_LOCATION set"
    )
  return "" if PY.exists() else f"APEX grading venv not found: {PY}"


def _world_zip(key: str):
  """The zip of the actor's starting world, as the archived grader passed it for the initial

  snapshot. Materialization indexes them under <data>/_worlds/apex/index.json;
  without the
  index the initial snapshot is empty, which scores file-type tasks about 0.08
  lower.
  """
  try:
    idx = json.loads((DATA / "_worlds" / "apex" / "index.json").read_text())
    stem = idx["idx2zip"].get(str(int(key.split("_")[0])))
    path = Path(idx["zip_paths"][stem]) if stem else None
  except (OSError, KeyError, ValueError, json.JSONDecodeError):
    return None
  return path if path and path.exists() else None


def _task_for(key: str) -> dict:
  m = re.fullmatch(r"(\d{3})_(IB|MC|Law)", key)
  if not m:
    raise ValueError(f"bad apex key {key!r}")
  t = _tasks()[int(m.group(1))]
  if DOMAIN[t["domain"]] != m.group(2):
    raise ValueError(
        f"key {key} domain mismatch with HF task {t['task_id']} ({t['domain']})"
    )
  return t


def _verifiers(t: dict) -> list[dict]:
  return [
      {
          "verifier_id": c["verifier_id"],
          "verifier_version": 1,
          "world_id": t["world_id"],
          "task_id": t["task_id"],
          "eval_config_id": "ec_output_llm",
          "verifier_values": {
              "criteria": c["criteria"],
              "is_primary_objective": i == 0,
          },
          "verifier_index": i,
          "verifier_dependencies": None,
      }
      for i, c in enumerate(t.get("rubric") or [])
  ]


def grade(key: str, deliverables: Path, timeout: int = 1800, **_) -> dict:
  ans = deliverables / "answer.md"
  if not ans.exists():
    return {
        "score": 0.0,
        "error": "no answer.md in deliverables",
        "grader": GRADER,
    }
  answer = ans.read_text(errors="replace").strip()
  if not answer:
    return {"score": 0.0, "error": "empty answer.md", "grader": GRADER}
  t = _task_for(key)
  verifiers = _verifiers(t)
  if not verifiers:
    return {
        "score": 0.0,
        "error": f"task {t['task_id']} has no rubric",
        "grader": GRADER,
    }
  td = Path(tempfile.mkdtemp(prefix="vh_apex_grade_", dir="/var/tmp"))
  try:
    traj = td / "trajectory.json"
    traj.write_text(
        json.dumps({
            "messages": [
                {"role": "user", "content": t["prompt"]},
                {"role": "assistant", "content": answer},
            ],
            "output": None,
            "status": "completed",
            "time_elapsed": 0.0,
        })
    )
    # Snapshots. The initial one stays empty; the final one carries whatever the bundle
    # holds BESIDES answer.md, so a deliverable that lives in a file (a workbook, a deck,
    # a document) reaches the judge as a created artifact instead of vanishing. For a
    # message_in_console task the bundle is answer.md alone and the final zip stays empty,
    # i.e. behaviour is unchanged for those tasks. (Without this, file-type tasks were
    # unscoreable by construction and revisions to those files were invisible.)
    initial = _world_zip(key) or td / "empty_snapshot.zip"
    if not initial.exists():
      with zipfile.ZipFile(initial, "w"):
        pass
    final = td / "final_snapshot.zip"
    n_art = 0
    with zipfile.ZipFile(final, "w", zipfile.ZIP_DEFLATED) as z:
      for f in sorted(deliverables.rglob("*")):
        if not f.is_file() or f.name == "answer.md" or is_view(f.name):
          continue
        z.write(
            f, f"filesystem/{f.relative_to(deliverables)}"
        )  # real snapshots root everything at filesystem/
        n_art += 1
    vf = td / "verifiers.json"
    vf.write_text(json.dumps(verifiers, indent=2))
    out = td / "grades.json"
    run_id = f"vh_{key}_{td.name.rsplit('_', 1)[-1]}"
    cmd = [
        str(PY),
        "-m",
        "runner.main",
        "--grading-run-id",
        run_id,
        "--trajectory-id",
        run_id,
        "--initial-snapshot",
        str(initial),
        "--final-snapshot",
        str(final),
        "--trajectory",
        str(traj),
        "--grading-settings",
        str(_grading_settings()),
        "--verifiers",
        str(vf),
        "--eval-configs",
        str(CONFIGS / "eval_configs.json"),
        "--scoring-config",
        str(CONFIGS / "scoring_config.json"),
        "--output",
        str(out),
    ]
    keys = _api_keys()
    env = {**os.environ, "PYTHONPATH": "."}
    if keys:
      env["GEMINI_API_KEY"] = keys[next(_KEY_RR) % len(keys)]
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(GRADING),
        env=env,
    )
    if not out.exists():
      return {
          "score": 0.0,
          "error": (p.stderr or p.stdout)[-800:],
          "grader": GRADER,
      }
    g = json.loads(out.read_text())
  finally:
    shutil.rmtree(td, ignore_errors=True)
  vr = g.get("verifier_results") or []
  status = g.get("grading_run_status")
  if status != "completed" or len(vr) != len(verifiers):
    err = (g.get("scoring_results") or {}).get(
        "scoring_method_result_values", {}
    ).get("error") or status
    return {
        "score": 0.0,
        "error": f"grading_run_status={status}, {len(vr)}/{len(verifiers)} verifiers: {err}"[
            :800
        ],
        "grader": GRADER,
        "rubrics": vr,
    }
  score = sum(float(v.get("score") or 0.0) for v in vr) / len(vr)
  return {
      "score": score,
      "detail": {
          "task_id": t["task_id"],
          "n_verifiers": len(vr),
          "passed": sum(1 for v in vr if (v.get("score") or 0) > 0),
          "final_score": (g.get("scoring_results") or {}).get("final_score"),
      },
      "rubrics": [
          {
              "verifier_id": v["verifier_id"],
              "criteria": verifiers[i]["verifier_values"]["criteria"],
              "score": v.get("score"),
              "status": v.get("status"),
              "judge_grade": (
                  (v.get("verifier_result_values") or {}).get("judge_grade")
              ),
              "rationale": (
                  (v.get("verifier_result_values") or {}).get("grade_rationale")
              ),
          }
          for i, v in enumerate(vr)
      ],
      "grader": GRADER,
  }
