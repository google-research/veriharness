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
"""SpreadsheetBench-2 adapter.

dataset.json: ONLY `instruction` and `spreadsheet_path` are read —
`golden_response_path` and `answer_position` are the answer key. Pool dirs:
ONLY `{tid}_output.*` and the rendered trajectory move; `grade.json` carries
per-cell ground truth (`cell_errors`) and never does.
"""

import json
import re

from harness.materialize.base import Rollout, SRCROOT, Task
from harness.materialize.renderers import render_sb2_traj

SB2 = SRCROOT / "benchmarks/sb2"
POOLS = {"flash": "flash_high", "opus": "opus_high"}


def _specs() -> dict:
  out = {}
  for cat in sorted((SB2 / "official/data").iterdir()):
    ds = cat / "dataset.json"
    if not ds.exists():
      continue
    for rec in json.loads(ds.read_text()):
      key = f"{cat.name}__{rec['id']}"
      out[key] = (rec.get("instruction", ""), cat / rec["spreadsheet_path"])
  return out


def iter_tasks(pool: str):
  prefix = POOLS[pool]
  grades = json.loads((SB2 / "grades/grades.json").read_text())
  specs = _specs()
  seeds_all = {
      d.name
      for d in (SB2 / "pools").iterdir()
      if re.fullmatch(prefix + r"_s\d\d", d.name)
  }
  for key in sorted(grades):
    seeds = sorted(
        s for s in grades[key] if s.startswith(prefix) and s in seeds_all
    )
    if len(seeds) < 2 or key not in specs:
      continue
    instruction, input_file = specs[key]
    tid = key.split("__", 1)[1]
    task = Task(key=key, spec=instruction)
    if input_file.exists():
      task.workspace.append((input_file, input_file.name))
    for seed in seeds:
      d = SB2 / "pools" / seed / key
      files = (
          [(p, p.name) for p in sorted(d.glob(f"{tid}_output.*"))]
          if d.is_dir()
          else []
      )
      tf = d / "traj" / f"{tid}.traj"
      score = grades[key][seed].get("accuracy")
      task.rollouts[seed] = Rollout(
          seed=seed,
          score=float(score) if score is not None else None,
          files=files,
          traj=(lambda f=tf: render_sb2_traj(f)) if tf.exists() else None,
      )
    yield task
