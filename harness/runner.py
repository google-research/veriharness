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

#!/usr/bin/env python3
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
"""Batch runner: drive materialized tasks through the driver with one global work

pool, rate-limited per model lane and per cell (a cell is one bench:pool pair).
Resumable.

    python3 -m harness.runner --run-name R --cells sb2:flash sb2:opus apex:flash
    ...
        [--sample N | --fraction F] [--seed S] [--only KEY ...] [--only-file F]
        [--limit N]
        [--max-flash 25] [--max-opus 45] [--cell-cap apex=8,wb=10,default=12]
        [--contract artifact|pick-only] [--skill NAME ... | --no-skills]

Layout: runs/R/<bench>_<pool>/<task-key>/ is a full copy of the task workspace
(the
verifier may modify it; the data root stays pristine) plus driver.log and the
records; runs/R/<bench>_<pool>/run.json records the cell's selection and
settings.
Resume: a task with finish.json is skipped; one without is wiped and re-staged,
unless --skip-inflight says another driver is still active on it.

Why two limits: providers throttle on tokens per minute, so large-context cells
(apex, wb) must run at lower concurrency than small ones even within one lane,
while lane totals guard the per-model quota. Each driver runs its two
investigations concurrently, so a slot holds up to two model sessions.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import threading
import time

from harness import config
from harness.views import render_views

DEFAULT_LANE_MAX = {"flash": 25, "opus": 45}
DEFAULT_CELL_CAP = {
    "apex": 8,
    "wb": 10,
    "sb2": 14,
    "jb": 14,
    "wsb": 14,
    "default": 12,
}


def last_activity(ws: Path) -> float:
  files = list((ws / "session").rglob("*.jsonl")) + [ws / "driver.log"]
  return max((f.stat().st_mtime for f in files if f.exists()), default=0.0)


def run_task(
    src: Path,
    ws: Path,
    lane: str,
    driver_args: list[str],
    skip_inflight_min: int,
) -> str:
  if (ws / "finish.json").exists():
    return "skip"
  if (
      ws.exists()
      and skip_inflight_min
      and time.time() - last_activity(ws) < skip_inflight_min * 60
  ):
    return "inflight"
  if ws.exists():
    shutil.rmtree(ws)
  # symlinks=True: workspace/world etc. are links into <data>/_worlds, which the jail binds read-only.
  shutil.copytree(src, ws, symlinks=True)
  # Pools materialized by an older renderer get the current views here. The task inputs are
  # few and carry the template's notes, so their views are always refreshed.
  render_views(ws / "workspace", refresh=True)
  render_views(ws / "rollouts")
  cmd = [
      sys.executable,
      "-m",
      "harness.driver",
      str(ws),
      *config.LANES[lane],
      *driver_args,
  ]
  with open(ws / "run.out", "w", encoding="utf-8") as out:
    rc = subprocess.run(
        cmd, stdout=out, stderr=subprocess.STDOUT, cwd=config.REPO
    ).returncode
  return "ok" if (ws / "finish.json").exists() else f"no-finish(rc={rc})"


def select_keys(bench: str, pool: str, args) -> list[str]:
  tasks_dir = config.DATA / bench / pool / "tasks"
  keys = sorted(p.name for p in tasks_dir.iterdir() if p.is_dir())
  only = set(args.only)
  if args.only_file:
    with open(args.only_file, encoding="utf-8") as f:
      only |= {line.rstrip("\n") for line in f if line.strip()}
  if only:
    keys = [k for k in keys if k in only]
  if args.limit:
    keys = keys[: args.limit]
  if args.sample and args.sample < len(keys):
    keys = sorted(random.Random(args.seed).sample(keys, args.sample))
  if 0 < args.fraction < 1:
    keys = sorted(
        random.Random(args.seed).sample(
            keys, max(1, round(len(keys) * args.fraction))
        )
    )
  return keys


def parse_caps(spec: str) -> dict:
  caps = dict(DEFAULT_CELL_CAP)
  for item in filter(None, (spec or "").split(",")):
    k, v = item.split("=")
    caps[k.strip()] = int(v)
  return caps


def driver_processes() -> dict:
  """Driver processes on this host, per lane.

  Those that are not ours (e.g. left behind by a killed runner) consume the same
  provider quota, so they count against the lane caps.
  """
  seen = dict.fromkeys(config.LANES, 0)
  try:
    ps = subprocess.run(
        ["pgrep", "-af", "harness.driver"], capture_output=True, text=True
    ).stdout
  except OSError:
    return seen
  for line in ps.splitlines():
    for lane, flags in config.LANES.items():
      if flags[flags.index("--model") + 1] in line:
        seen[lane] += 1
  return seen


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description="VeriHarness batch runner")
  ap.add_argument("--cells", nargs="+", required=True, metavar="BENCH:POOL")
  ap.add_argument(
      "--run-name", required=True, help="outputs go to <runs>/<run-name>/"
  )
  ap.add_argument(
      "--contract", choices=["artifact", "pick-only"], default="artifact"
  )
  ap.add_argument(
      "--lane",
      choices=list(config.LANES),
      default=None,
      help=(
          "verifier model for ALL cells (default: each cell's own pool, i.e."
          " the same model that generated the rollouts)"
      ),
  )
  ap.add_argument("--max-flash", type=int, default=DEFAULT_LANE_MAX["flash"])
  ap.add_argument("--max-opus", type=int, default=DEFAULT_LANE_MAX["opus"])
  ap.add_argument(
      "--cell-cap",
      default="",
      help="bench=N,... overrides (key 'default' for the rest)",
  )
  ap.add_argument(
      "--only", action="append", default=[], help="task key (repeatable)"
  )
  ap.add_argument(
      "--only-file",
      help="file with one task key per line (keys may contain spaces)",
  )
  ap.add_argument("--limit", type=int, default=0)
  ap.add_argument(
      "--sample",
      type=int,
      default=0,
      help="per-cell random sample of N tasks (see --seed)",
  )
  ap.add_argument(
      "--fraction",
      type=float,
      default=0.0,
      help="per-cell random fraction of the tasks, e.g. 0.2",
  )
  ap.add_argument("--seed", type=int, default=0)
  ap.add_argument("--turn-timeout", type=int)
  ap.add_argument("--task-timeout", type=int)
  ap.add_argument(
      "--skip-inflight",
      type=int,
      default=45,
      metavar="MIN",
      help=(
          "leave alone task dirs active within the last MIN minutes (default"
          " 45; 0 disables)"
      ),
  )
  ap.add_argument(
      "--skill",
      action="append",
      default=[],
      help=(
          "skill name or directory (repeatable; default: the built-in library)"
      ),
  )
  ap.add_argument(
      "--no-skills", action="store_true", help="run with an empty skill library"
  )
  ap.add_argument(
      "--driver-arg",
      action="append",
      default=[],
      help=(
          "extra flag passed verbatim to the driver (e.g. --driver-arg=--env"
          " --driver-arg=native)"
      ),
  )
  args = ap.parse_args(argv)

  cells = [tuple(c.split(":", 1)) for c in args.cells]
  for bench, pool in cells:
    if bench not in config.BENCHES:
      print(f"error: unknown bench '{bench}'", file=sys.stderr)
      return 2
    if pool not in config.LANES and not args.lane:
      print(f"error: pool '{pool}' names no lane; pass --lane", file=sys.stderr)
      return 2
  lane_of = {pool: args.lane or pool for _, pool in cells}
  if any(lane in config.PROXIED_LANES for lane in lane_of.values()):
    subprocess.run([str(config.SCRIPTS_DIR / "litellm_up.sh")], check=True)

  driver_args = ["--contract", args.contract]
  if args.turn_timeout:
    driver_args += ["--turn-timeout", str(args.turn_timeout)]
  if args.task_timeout:
    driver_args += ["--task-timeout", str(args.task_timeout)]
  if args.no_skills:
    driver_args.append("--no-skills")
  for skill in args.skill:
    driver_args += ["--skill", skill]
  driver_args += args.driver_arg
  caps = parse_caps(args.cell_cap)
  lane_max = {"flash": args.max_flash, "opus": args.max_opus}

  # Per-cell selection + run.json.
  root = config.RUNS / args.run_name
  plan, cell_cap = [], {}
  for bench, pool in cells:
    cell_dir = root / f"{bench}_{pool}"
    cell_dir.mkdir(parents=True, exist_ok=True)
    keys = select_keys(bench, pool, args)
    cell_cap[(bench, pool)] = caps.get(bench, caps["default"])
    (cell_dir / "run.json").write_text(
        json.dumps(
            {
                "bench": bench,
                "pool": pool,
                "lane": lane_of[pool],
                "contract": args.contract,
                "n_tasks": len(keys),
                "sample": args.sample,
                "fraction": args.fraction,
                "seed": args.seed,
                "skills": (
                    "none" if args.no_skills else (args.skill or "default")
                ),
                "cell_cap": cell_cap[(bench, pool)],
                "lane_max": lane_max,
                "driver_args": driver_args,
                "keys": keys,
            },
            indent=1,
        )
    )
    plan.append([(bench, pool, cell_dir, k) for k in keys])
    print(
        f"{bench}/{pool}: tasks={len(keys)} cap={cell_cap[(bench, pool)]}",
        flush=True,
    )

  # Round-robin interleave so no cell starves; then a slot-aware scheduler.
  queue = [
      p[i]
      for i in range(max((len(p) for p in plan), default=0))
      for p in plan
      if i < len(p)
  ]
  total = len(queue)
  lock = threading.Lock()
  in_use_lane = dict.fromkeys(config.LANES, 0)
  in_use_cell = dict.fromkeys(cell_cap, 0)
  counts, done = {}, [0]

  def work(bench, pool, cell_dir, key):
    try:
      status = run_task(
          config.DATA / bench / pool / "tasks" / key,
          cell_dir / key,
          lane_of[pool],
          driver_args,
          args.skip_inflight,
      )
    except Exception as e:  # noqa: BLE001
      status = f"error({e})"
    with lock:
      in_use_lane[lane_of[pool]] -= 1
      in_use_cell[(bench, pool)] -= 1
      counts[status] = counts.get(status, 0) + 1
      done[0] += 1
      print(f"[{done[0]}/{total}] {bench}/{pool} {key}: {status}", flush=True)

  print(
      f"scheduling {total} tasks; lane max {lane_max}; cell caps {cell_cap}",
      flush=True,
  )
  with ThreadPoolExecutor(max_workers=sum(lane_max.values())) as ex:
    pending = queue
    while pending:
      rest = []
      seen = driver_processes()
      with lock:
        ext = {lane: max(0, n - in_use_lane[lane]) for lane, n in seen.items()}
      for item in pending:
        bench, pool, _, _ = item
        lane = lane_of[pool]
        with lock:
          ok = (
              in_use_lane[lane] + ext[lane] < lane_max[lane]
              and in_use_cell[(bench, pool)] < cell_cap[(bench, pool)]
          )
          if ok:
            in_use_lane[lane] += 1
            in_use_cell[(bench, pool)] += 1
        if ok:
          ex.submit(work, *item)
        else:
          rest.append(item)
      pending = rest
      if pending:
        time.sleep(3)
  print("done:", json.dumps(counts), flush=True)
  return 0 if set(counts) <= {"ok", "skip", "inflight"} else 1


if __name__ == "__main__":
  sys.exit(main())
