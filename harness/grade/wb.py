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

"""WorkBuddy: a NEW deliverable (agent.patch [+ artifacts/]) re-graded by the benchmark's own

CompositeVerifier, on the `reward` scale of data/wb/<pool>/meta.json.

What runs (all upstream code, nothing re-implemented):
  * the task's env image (data/_worlds/wb/<task>/.exported names the one we
  exported from) is
    started with `sleep infinity`; the deliverable is materialised in its
    pristine /workspace:
    agent.patch is `git apply`'d against the image's HEAD ("initial setup"
    commit — the same base
    the verifier diffs against), escalating strict -> --recount -> --recount -3
    (never partial);
    binary stubs ("Binary files ... differ", not replayable) are dropped from
    the patch and the
    files come from artifacts/ instead, mapped back through tests/judge.yaml
    (raw name =
    safe(id)+suffix, as the office extractor wrote them);
  * `workbuddy_bench.judge.profiles.dispatcher._run_registry_verifier` is driven
  in-process
    (under the benchmark's own .venv python) with a minimal Harbor-shaped
    verifier: a docker
    exec/cp environment (verifier user dev for code, root for office/web —
    configs/bench) and a
    trial dir under /var/tmp. That loads datasets/<ds>/shared/verifier/plugin.py
    and does exactly
    what a trial's verifier phase does: upload tests, regenerate agent.patch,
    run the rule script
    (verifier.py / pytest), the office host-side rubric LLM judge, or the web
    in-container
    rule+LLM/VLM+agent stages, then write
    verifier/{score.json,reward.json,llm_judge.json};
  * the LLM route is the benchmark's own proxy (workbuddy_bench.proxy, slug
    vertex/gemini-3.5-flash -> the benchmark's litellm endpoint, injecting the
    model's params exactly as the
    archived runs did), started once per process on a free port with its
    config/logs in
    /var/tmp/vh_wb_proxy_*; code tasks have no judge (bench default disabled)
    and get no route.

Score = score.json `reward` (code: rule pass rate; office: 0.8*rule + 0.2*LLM
rubric mean; web:
the fixed-judge report score). Limitations: the LLM/VLM/agent judges are
stochastic (office
±0.2/n_rubrics granularity); web needs the image's browser stack and the
in-container judge, so it
is the slowest; images must exist locally (no rebuild). Temp dirs:
/var/tmp/vh_wb_grade_*,
removed unless grade(..., keep=True). Nothing is written under the benchmark
tree.
"""

import atexit
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

# This file also runs as a script under the benchmark's own interpreter (see grade():
# `VENV_PY __file__ --driver`), where the harness package is not importable and the host-side
# locations below are not needed.
if __name__ != "__main__":
  from harness.config import DATA, bench_root

  WB = bench_root() / "benchmarks" / "workbuddy" / "workbuddy-bench"
  VENV_PY = WB / ".venv" / "bin" / "python"
  DATASETS = WB / "datasets"
  WORLDS = DATA / "_worlds" / "wb"
DS_NAME = {
    "code": "wb-bench-code-v1.0",
    "office": "wb-bench-office-v1.0",
    "web": "wb-bench-web-v1.0",
}
GRADER = "wb/CompositeVerifier"
JUDGE_SLUG = (  # configs/models/vertex/gemini-3.5-flash.yaml
    "vertex/gemini-3.5-flash"
)
JUDGE_DOMAINS = ("office", "web")  # code: llm_judge disabled (configs/bench)
VERIFIER_USER = {
    "code": "dev",
    "office": "root",
    "web": "root",
}  # configs/bench/{_default,office,web}.yaml
BENCH_VERIFIER_ENV = {
    "web": {
        "WEB_BENCH_LLM_JUDGE_MODE": "full",
        "WEB_BENCH_LLM_TIMEOUT_SEC": "1200",
    }
}
DRIVER_TIMEOUT = 4200  # task verifier timeout 1800 x2 + judge + margin


# ----------------------------------------------------------------------------- host side (any python)
def _dotenv() -> dict:
  env = {}
  for ln in (WB / ".env").read_text().splitlines():
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
      k, v = ln.split("=", 1)
      env[k.strip()] = v.strip().strip('"')
  return env


def _wb_env() -> dict:
  return {**os.environ, **_dotenv(), "PYTHONPATH": str(WB / "src")}


def _image_for(tname: str):
  mark = WORLDS / tname / ".exported"
  cands = [mark.read_text().strip()] if mark.exists() else []
  images = subprocess.run(
      ["docker", "images", "--format", "{{.Repository}}"],
      capture_output=True,
      text=True,
  ).stdout.split()
  if cands and cands[0] in images:
    return cands[0]
  low = tname.lower()
  hits = sorted(
      i
      for i in images
      if i.endswith("__env-main") and low.startswith(i.rsplit("__", 2)[0])
  )
  return hits[0] if hits else None


_proxy = {"url": None, "proc": None, "dir": None}
_proxy_lock = threading.Lock()


def _free_port() -> int:
  with socket.socket() as s:
    s.bind(("", 0))
    return s.getsockname()[1]


def _healthy(port: int) -> bool:
  try:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/health", timeout=2
    ) as r:
      return json.load(r).get("status") == "ok"
  except Exception:  # noqa: BLE001
    return False


def _stop_proxy():
  p = _proxy["proc"]
  if p and p.poll() is None:
    p.terminate()
    try:
      p.wait(10)
    except subprocess.TimeoutExpired:
      p.kill()
  if _proxy["dir"]:
    shutil.rmtree(_proxy["dir"], ignore_errors=True)
  _proxy.update(url=None, proc=None, dir=None)


def _proxy_url() -> str:
  """Container-reachable root URL of a private judge proxy (started once per process).

  Same route the archived runs used: the model's params are injected by the
  proxy, litellm upstream.
  """
  with _proxy_lock:
    if _proxy["url"] and _proxy["proc"].poll() is None:
      return _proxy["url"]
    _stop_proxy()
    port, pdir = _free_port(), Path(
        tempfile.mkdtemp(prefix="vh_wb_proxy_", dir="/var/tmp")
    )
    cfg = pdir / "proxy.yaml"
    cfg.write_text(
        json.dumps({
            "proxy": {
                "host": "0.0.0.0",
                "port": port,
                "log_dir": str(pdir),
                "log_enabled": False,
                "max_concurrent": 64,
                "shared": True,
                "routes": [],
            }
        })
    )  # JSON is YAML
    env = _wb_env()
    r = subprocess.run(
        [
            str(VENV_PY),
            "-m",
            "workbuddy_bench.runner.proxy_config",
            "--judge-only",
            "--judge-slug",
            JUDGE_SLUG,
            "--judge-model-config",
            str(WB / "configs" / "models" / f"{JUDGE_SLUG}.yaml"),
            "--shared",
            str(cfg),
            "--port",
            str(port),
            "--log-dir",
            str(pdir),
            "--max-concurrent",
            "64",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(WB),
    )
    if r.returncode:
      raise RuntimeError(
          f"proxy_config failed: {(r.stderr or r.stdout)[-600:]}"
      )
    log = open(pdir / "proxy.log", "ab")
    _proxy["proc"] = subprocess.Popen(
        [
            str(VENV_PY),
            "-m",
            "workbuddy_bench.proxy",
            "--config",
            str(cfg),
            "--port",
            str(port),
            "--log-dir",
            str(pdir),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(WB),
    )
    _proxy["dir"] = pdir
    atexit.register(_stop_proxy)
    for _ in range(60):
      if _healthy(port):
        _proxy["url"] = f"http://host.docker.internal:{port}"
        return _proxy["url"]
      if _proxy["proc"].poll() is not None:
        break
      time.sleep(0.5)
    raise RuntimeError(f"judge proxy did not come up; see {pdir}/proxy.log")


def grade(key: str, deliverables: Path, keep: bool = False, **_) -> dict:
  dom, _, tname = key.partition("__")
  if dom not in DS_NAME:
    return {"score": 0.0, "error": f"unknown domain {dom}", "grader": GRADER}
  task_dir = DATASETS / DS_NAME[dom] / "tasks" / tname
  if not (task_dir / "task.toml").exists():
    return {"score": 0.0, "error": f"no task dir {task_dir}", "grader": GRADER}
  if not deliverables.is_dir():
    return {
        "score": 0.0,
        "error": f"no deliverables dir {deliverables}",
        "grader": GRADER,
    }
  image = _image_for(tname)
  if not image:
    return {
        "score": 0.0,
        "error": f"no local env image for {tname}",
        "grader": GRADER,
    }
  tmp = Path(tempfile.mkdtemp(prefix="vh_wb_grade_", dir="/var/tmp"))
  cname = f"vh_wb_{tmp.name[len('vh_wb_grade_'):]}"
  try:
    shutil.copytree(deliverables, tmp / "deliverable", symlinks=False)
    cmd = [
        str(VENV_PY),
        __file__,
        "--driver",
        "--domain",
        dom,
        "--task-dir",
        str(task_dir),
        "--image",
        image,
        "--deliverable",
        str(tmp / "deliverable"),
        "--trial-dir",
        str(tmp / "trial"),
        "--container",
        cname,
        "--proxy-url",
        _proxy_url() if dom in JUDGE_DOMAINS else "",
    ]
    try:
      p = subprocess.run(
          cmd,
          capture_output=True,
          text=True,
          env=_wb_env(),
          cwd=str(WB),
          timeout=DRIVER_TIMEOUT,
      )
    except subprocess.TimeoutExpired:
      return {
          "score": 0.0,
          "error": f"driver timed out after {DRIVER_TIMEOUT}s",
          "grader": GRADER,
      }
    finally:
      subprocess.run(["docker", "rm", "-f", cname], capture_output=True)
    line = next(
        (
            ln
            for ln in reversed(p.stdout.splitlines())
            if ln.startswith("VH_RESULT ")
        ),
        None,
    )
    if line is None:
      return {
          "score": 0.0,
          "error": (
              f"driver produced no result (rc={p.returncode}):"
              f" {(p.stderr or p.stdout)[-800:]}"
          ),
          "grader": GRADER,
      }
    res = json.loads(line[len("VH_RESULT ") :])
    if keep:
      res.setdefault("detail", {})["kept"] = str(tmp)
    return res
  finally:
    if not keep:
      shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------- driver (benchmark .venv python)
_BINARY_STUB = re.compile(r"^Binary files .* differ$", re.M)


def _split_patch(text: str):
  """(kept_patch_text, [paths of dropped binary-stub sections])."""
  parts = re.split(r"(?m)^(?=diff --git )", text)
  kept, dropped = [], []
  for sec in parts:
    if not sec.startswith("diff --git "):
      if sec.strip():
        kept.append(sec)
      continue
    if _BINARY_STUB.search(sec) and "GIT binary patch" not in sec:
      m = re.match(r"diff --git a/(.*?) b/(.*)", sec.splitlines()[0])
      dropped.append(m.group(2) if m else "?")
      continue
    kept.append(sec)
  out = "".join(kept)
  return (out if out.endswith("\n") or not out else out + "\n"), dropped


def _artifact_targets(task_dir: Path, art_dir: Path, dropped: list) -> tuple:
  """artifacts/<name> -> workspace-relative path: judge.yaml (id,path) first, then a dropped binary stub

  with the same basename, else the artifact's own relative name.
  """
  import yaml

  safe = lambda v: re.sub(r"[^A-Za-z0-9_.-]+", "_", v).strip("_") or "artifact"  # noqa: E731
  by_raw = {}
  jy = task_dir / "tests" / "judge.yaml"
  if jy.exists():
    for a in (yaml.safe_load(jy.read_text()) or {}).get("artifacts") or []:
      if isinstance(a, dict) and a.get("id") and a.get("path"):
        sid, suf = safe(str(a["id"])), Path(str(a["path"])).suffix
        by_raw[f"{sid}{suf}" if suf and not sid.endswith(suf) else sid] = str(
            a["path"]
        )
  plan, warn = [], []
  for f in sorted(p for p in art_dir.rglob("*") if p.is_file()):
    if f.name.endswith(
        (".cells.tsv", ".text.txt")
    ):  # the harness's own rendered views, never artifacts
      continue
    rel = f.relative_to(art_dir).as_posix()
    if rel in by_raw:
      plan.append((f, by_raw[rel]))
    elif any(Path(d).name == f.name for d in dropped):
      plan.append((f, next(d for d in dropped if Path(d).name == f.name)))
    else:
      plan.append((f, rel))
      warn.append(f"artifact {rel}: no judge.yaml/patch mapping, copied as-is")
  return plan, warn


def _driver(a) -> dict:
  import asyncio
  import tomllib
  from types import SimpleNamespace as NS
  from harbor.environments.base import ExecResult
  from harbor.environments.capabilities import EnvironmentCapabilities
  from harbor.models.task.config import TaskOS
  from workbuddy_bench.judge.profiles.dispatcher import _run_registry_verifier

  task_dir, dlv, trial = (
      Path(a.task_dir),
      Path(a.deliverable),
      Path(a.trial_dir),
  )
  cid, user = a.container, VERIFIER_USER[a.domain]
  (trial / "verifier").mkdir(parents=True)
  detail = {"image": a.image, "verifier_user": user, "warnings": []}

  def sh(*args, check=True, **kw):
    r = subprocess.run(list(args), capture_output=True, text=True, **kw)
    if check and r.returncode:
      raise RuntimeError(f"{args[:3]} failed: {(r.stderr or r.stdout)[-600:]}")
    return r

  def dexec(cmd, u="root", check=True, cwd=None):
    return sh(
        "docker",
        "exec",
        *(["-w", cwd] if cwd else []),
        "-u",
        u,
        cid,
        "bash",
        "-c",
        cmd,
        check=check,
    )

  class Env:
    os = TaskOS.LINUX
    capabilities = EnvironmentCapabilities(mounted=False)

    async def exec(
        self, command, cwd=None, env=None, timeout_sec=None, user=None
    ):
      argv = [
          "docker",
          "exec",
          *(["-w", cwd] if cwd else []),
          "-u",
          str(user if user is not None else self.default_user),
      ]
      for k, v in (env or {}).items():
        argv += ["-e", f"{k}={v}"]
      argv += [cid, "bash", "-c", command]
      p = await asyncio.create_subprocess_exec(
          *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
      )
      try:
        out, err = await asyncio.wait_for(p.communicate(), timeout_sec)
      except asyncio.TimeoutError:
        p.kill()
        raise
      return ExecResult(
          stdout=out.decode(errors="replace"),
          stderr=err.decode(errors="replace"),
          return_code=p.returncode,
      )

    async def upload_dir(self, source_dir, target_dir):
      dexec(f"mkdir -p '{target_dir}'")
      sh("docker", "cp", f"{source_dir}/.", f"{cid}:{target_dir}")

    async def download_dir(self, source_dir, target_dir):
      Path(target_dir).mkdir(parents=True, exist_ok=True)
      sh("docker", "cp", f"{cid}:{source_dir}/.", str(target_dir))

  env = Env()
  env.default_user = user

  # -- container: same image, same limits as the task declares; host gateway for the judge route
  tcfg = tomllib.loads((task_dir / "task.toml").read_text())
  ecfg = tcfg.get("environment") or {}
  lim = ([f"--cpus={ecfg['cpus']}"] if ecfg.get("cpus") else []) + (
      [f"--memory={ecfg['memory_mb']}m"] if ecfg.get("memory_mb") else []
  )
  sh(
      "docker",
      "run",
      "-d",
      "--name",
      cid,
      "--add-host",
      "host.docker.internal:host-gateway",
      *lim,
      "--entrypoint",
      "sleep",
      a.image,
      "infinity",
  )
  dexec(
      "if ! id dev >/dev/null 2>&1; then useradd -m -s /bin/bash dev; fi; mkdir"
      " -p /workspace /logs/verifier /logs/agent; git config --system --add"
      " safe.directory '*' || true"
  )

  # -- materialise the deliverable in /workspace
  patch_src = dlv / "agent.patch"
  text = patch_src.read_text(errors="replace") if patch_src.exists() else ""
  kept, dropped = _split_patch(text)
  detail["dropped_binary_stubs"] = dropped
  if kept.strip():
    (dlv / "_apply.patch").write_text(kept)
    sh("docker", "cp", str(dlv / "_apply.patch"), f"{cid}:/tmp/_apply.patch")
    level, last = None, ""
    for name, flags in (
        ("strict", ""),
        ("recount", "--recount"),
        ("recount3", "--recount -3"),
    ):
      r = dexec(
          f"git apply --whitespace=nowarn --binary {flags} /tmp/_apply.patch",
          check=False,
          cwd="/workspace",
      )
      if r.returncode == 0:
        level = name
        break
      last = r.stderr
    detail["apply_level"] = level
    if level is None:
      return {
          "score": 0.0,
          "error": f"agent.patch did not apply: {last[-600:]}",
          "detail": detail,
          "grader": GRADER,
      }
  else:
    detail["apply_level"] = "no_patch"
  art_dir = dlv / "artifacts"
  if art_dir.is_dir():
    plan, warn = _artifact_targets(task_dir, art_dir, dropped)
    detail["warnings"] += warn
    for src, rel in plan:
      dexec(f"mkdir -p \"$(dirname '/workspace/{rel}')\"")
      sh("docker", "cp", str(src), f"{cid}:/workspace/{rel}")
    detail["artifacts_copied"] = [rel for _, rel in plan]
  dexec("chown -R dev /workspace /logs")

  # -- the benchmark's verifier, on a Harbor-shaped shim
  verifier_env = dict(BENCH_VERIFIER_ENV.get(a.domain, {}))
  if a.proxy_url:
    verifier_env.update({
        "WORKBUDDY_VERIFIER_LLM_BASE_URL": a.proxy_url.rstrip("/") + "/v1",
        "WORKBUDDY_VERIFIER_LLM_API_KEY": JUDGE_SLUG,
        "WORKBUDDY_VERIFIER_LLM_MODEL": JUDGE_SLUG,
    })
  ver = NS(
      task=NS(
          paths=NS(task_dir=task_dir, tests_dir=task_dir / "tests"),
          short_name=task_dir.name,
          config=NS(verifier=NS(env={})),
      ),
      trial_paths=NS(
          verifier_dir=trial / "verifier",
          reward_json_path=trial / "verifier" / "reward.json",
      ),
      environment=env,
      verifier_env=verifier_env,
      override_env={},
  )
  t0 = time.time()
  asyncio.run(_run_registry_verifier(ver))
  detail["verify_sec"] = round(time.time() - t0, 1)
  score = json.loads((trial / "verifier" / "score.json").read_text())
  for k in (
      "test_status",
      "tests_passed",
      "tests_total",
      "test_pass_rate",
      "llm_judge_component_score",
      "overall",
  ):
    if k in score:
      detail[k] = score[k]
  lj = trial / "verifier" / "llm_judge.json"
  if lj.exists():
    j = json.loads(lj.read_text())
    detail["llm_judge"] = {
        "status": j.get("judge_status"),
        "model": j.get("model"),
        "rubrics": {
            r.get("id"): r.get("verdict") for r in j.get("rubrics") or []
        },
    }
  diag = score.get("diagnostics") or {}
  if diag.get("engine_error"):
    detail["engine_error"] = {k: diag.get(k) for k in ("engine_error", "error")}
  return {
      "score": float(score.get("reward") or 0.0),
      "detail": detail,
      "grader": GRADER,
  }


def _main_driver():
  import argparse

  ap = argparse.ArgumentParser()
  for opt in (
      "--domain",
      "--task-dir",
      "--image",
      "--deliverable",
      "--trial-dir",
      "--container",
      "--proxy-url",
  ):
    ap.add_argument(opt, required=opt != "--proxy-url", default="")
  a = ap.parse_args(sys.argv[2:])
  try:
    res = _driver(a)
  except Exception as e:  # noqa: BLE001
    import traceback

    res = {
        "score": 0.0,
        "error": f"{type(e).__name__}: {e}",
        "detail": {"trace": traceback.format_exc()[-1500:]},
        "grader": GRADER,
    }
  finally:
    subprocess.run(["docker", "rm", "-f", a.container], capture_output=True)
  print("VH_RESULT " + json.dumps(res, default=str), flush=True)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--driver":
  _main_driver()
