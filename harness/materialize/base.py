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

"""Shared materialization machinery for all benchmarks.

A bench module supplies `iter_tasks(pool) -> Iterator[Task]`; this module writes
the self-contained workspace layout, anonymizes rollout labels, merges meta,
handles resume markers, and provides the CLI.

Layout written per task:
    <data>/<bench>/<pool>/tasks/<key>/
      spec/task.md
      workspace/...                       (task inputs, if any)
      rollouts/rNN/deliverables/...
      rollouts/rNN/trajectory/trajectory.txt
    <data>/<bench>/<pool>/meta.json         (scores + label->seed map; never in
    a run)
    <data>/<bench>/<pool>/.done/<key>       (resume markers)

Leak defense-in-depth: `copy_file`/`copy_tree` refuse to copy any file whose
name matches the answer-key blocklist, whatever a bench adapter asks for.
"""

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil

from harness.config import DATA, bench_root
from harness.views import render_views

SRCROOT = (
    bench_root()
)  # where the upstream benchmarks and the archived rollouts live

_BLOCK_NAMES = {
    "grades.json",
    "grade.json",
    "verifiers.json",
    "RUBRICS.json",
    "dataset.json",
    "task.toml",
}
_BLOCK_PREFIXES = ("rubrics_judge",)
_BLOCK_SUBSTR = ("golden",)
_BLOCK_DIRS = {"tests", "solution", "eval_result", "model_output", "model_traj"}


def _blocked(name: str) -> bool:
  low = name.lower()
  return (
      name in _BLOCK_NAMES
      or name.startswith(_BLOCK_PREFIXES)
      or any(s in low for s in _BLOCK_SUBSTR)
  )


def copy_file(src: Path, dst: Path, lenient: bool = False) -> None:
  if _blocked(src.name):
    if not lenient:
      raise RuntimeError(f"leak blocklist refuses to copy: {src}")
    # rollout-produced files may coincidentally match the blocklist;
    # warn loudly but copy — the adapter chose this path explicitly.
    print(f"WARNING: copying blocklist-named rollout file: {src}", flush=True)
  dst.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(src, dst)  # follows symlinks


def copy_tree(src: Path, dst: Path) -> None:
  for p in sorted(src.rglob("*")):
    rel = p.relative_to(src)
    if any(part in _BLOCK_DIRS for part in rel.parts):
      continue
    if p.is_file():
      if _blocked(p.name):
        continue  # silently skip inside trees; adapters exclude on purpose
      copy_file(p, dst / rel)


@dataclass
class Rollout:
  seed: str
  score: float | None
  files: list = field(default_factory=list)  # [(src_path, rel_name)]
  texts: list = field(default_factory=list)  # [(rel_name, callable_or_str)]
  traj: object = None  # callable -> str, or None
  traj_files: list = field(
      default_factory=list
  )  # [(src_path, rel_name)] raw trace files kept beside trajectory.txt


@dataclass
class Task:
  key: str
  spec: str
  workspace: list = field(default_factory=list)  # [(src_path, rel_name)]
  workspace_texts: list = field(default_factory=list)  # [(rel_name, text)]
  trees: list = field(default_factory=list)  # [(src_dir, rel_name_or_"")]
  rollouts: dict = field(default_factory=dict)  # seed -> Rollout
  links: list = field(
      default_factory=list
  )  # [(rel_name, abs_target)] symlinks into shared stores (data/_worlds)


def _text(v) -> str:
  return v() if callable(v) else v


def write_task(bench: str, pool: str, task: Task) -> dict:
  ws = DATA / bench / pool / "tasks" / task.key
  shutil.rmtree(ws, ignore_errors=True)
  (ws / "spec").mkdir(parents=True)
  (ws / "spec" / "task.md").write_text(task.spec, encoding="utf-8")
  (ws / "workspace").mkdir()
  for src, name in task.workspace:
    copy_file(Path(src), ws / "workspace" / name)
  for name, txt in task.workspace_texts:
    out = ws / "workspace" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_text(txt), encoding="utf-8")
  for srcdir, name in task.trees:
    copy_tree(
        Path(srcdir), ws / "workspace" / name if name else ws / "workspace"
    )
  for (
      name,
      target,
  ) in task.links:  # shared environment stores, mounted read-only by the jail
    (ws / "workspace" / name).symlink_to(
        Path(target).resolve(), target_is_directory=True
    )
  render_views(ws / "workspace")
  meta = {"rollouts": {}}
  for i, seed in enumerate(sorted(task.rollouts), 1):
    label = f"r{i:02d}"
    r = task.rollouts[seed]
    rdir = ws / "rollouts" / label
    (rdir / "deliverables").mkdir(parents=True)
    for src, name in r.files:
      copy_file(Path(src), rdir / "deliverables" / name, lenient=True)
    for name, txt in r.texts:
      out = rdir / "deliverables" / name
      out.parent.mkdir(parents=True, exist_ok=True)
      out.write_text(_text(txt), encoding="utf-8")
    if r.traj is not None or r.traj_files:
      (rdir / "trajectory").mkdir()
    if r.traj is not None:
      (rdir / "trajectory" / "trajectory.txt").write_text(
          _text(r.traj), encoding="utf-8"
      )
    for (
        src,
        name,
    ) in r.traj_files:  # e.g. the raw agent.json a benchmark's judge reads
      copy_file(Path(src), rdir / "trajectory" / name)
    render_views(rdir / "deliverables")
    meta["rollouts"][label] = {"seed": seed, "score": r.score}
  return meta


def run_cli(bench: str, pools: list, iter_tasks, argv=None) -> int:
  ap = argparse.ArgumentParser(description=f"materialize {bench}")
  ap.add_argument("--pool", choices=[*pools, "all"], default="all")
  ap.add_argument(
      "--only", action="append", default=[], help="task key (repeatable)"
  )
  ap.add_argument("--limit", type=int, help="max tasks per pool")
  a = ap.parse_args(argv)
  only = set(a.only) or None
  for pool in (pools if a.pool == "all" else [a.pool]):
    meta_file = DATA / bench / pool / "meta.json"
    merged = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    done = 0
    for task in iter_tasks(pool):
      if only and task.key not in only:
        continue
      if a.limit is not None and done >= a.limit:
        break
      marker = DATA / bench / pool / ".done" / task.key
      if marker.exists():
        done += 1
        continue
      if len(task.rollouts) < 2:
        continue
      merged[task.key] = write_task(bench, pool, task)
      marker.parent.mkdir(parents=True, exist_ok=True)
      marker.touch()
      done += 1
      print(
          f"[{bench}/{pool}] {done}: {task.key} "
          f"({len(task.rollouts)} rollouts)",
          flush=True,
      )
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(merged, indent=1, ensure_ascii=False))
    print(f"[{bench}/{pool}] total {done}; meta: {meta_file}", flush=True)
  return 0
