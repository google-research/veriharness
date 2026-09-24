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
"""SpreadsheetBench 2: deterministic categories (Debugging / Template / Financial_Model) are

graded as the official evaluation does: LibreOffice recalculation of the
delivered workbook
inside the benchmark's own docker image (the official `open_spreadsheet.py`),
then cell-by-cell
comparison with the golden workbook through the official `evaluation.py`
primitives (imported,
not copied), keeping every cell mismatch instead of the first. Score =
`accuracy` (0/1), the
field meta.json carries. Visualization needs the VLM checklist path and is not
wrapped (score
None). The dataset's input and golden workbooks must have been recalculated
once, as the
benchmark requires (setup_benchmarks.sh sb2 does this).
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from harness.config import bench_root

SB2 = bench_root() / "benchmarks" / "sb2" / "official"  # the upstream checkout
DATA = SB2 / "data"
IMAGE = os.environ.get(
    "VERIHARNESS_IMAGE_SB2_GRADER", "veriharness-sb2"
)  # the official image plus tqdm
DET_CATS = ("Debugging", "Template", "Financial_Model")
GRADER = "sb2/evaluation.py+recalc"
_datasets = {}


def _dataset(cat):
  if cat not in _datasets:
    _datasets[cat] = {
        str(d["id"]): d
        for d in json.loads((DATA / cat / "dataset.json").read_text())
    }
  return _datasets[cat]


def _recalc(stage: Path):
  """The official recalculation (LibreOffice through UNO, iterative calculation on, saved back as

  xlsx), run inside the benchmark image on a staging dir mounted separately, so
  nothing is
  written into the benchmark tree. The script processes every *output.xlsx under
  the dir.
  """
  cmd = [
      "docker",
      "run",
      "--rm",
      "--network",
      "none",
      "-u",
      f"{os.getuid()}:{os.getgid()}",
      "-e",
      "HOME=/tmp",
      "-v",
      f"{SB2}:/sb2:ro",
      "-v",
      f"{stage}:/stage",
      IMAGE,
      "python3",
      "/sb2/evaluation/open_spreadsheet.py",
      "--dir_path",
      "/stage",
  ]
  r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
  out = (r.stdout or "") + (r.stderr or "")
  bad = [
      m
      for m in (
          "Error [",
          "Initialization failed",
          "Batch processing error",
          "Cannot start LibreOffice",
      )
      if m in out
  ]
  if r.returncode != 0 or bad or "LibreOffice service started" not in out:
    raise RuntimeError(
        f"recalc failed (rc={r.returncode}, {bad}): {out[-600:]}"
    )


def _grade_det(data: dict, cat: str, outputs_dir: Path) -> dict:
  """The official per-item scoring (evaluation.process_single_item), with every cell mismatch kept."""
  sys.path.insert(0, str(SB2 / "evaluation"))
  import evaluation as ev  # noqa: E402  the official grading primitives

  dataset_path = DATA / cat
  input_file = str(dataset_path / data["spreadsheet_path"])
  gt_file = str(dataset_path / data["golden_response_path"])
  proc_file = str(outputs_dir / f"{data['id']}_output.xlsx")

  with_font_color = cat == "Debugging" and "Color" in data.get(
      "spreadsheet_path", ""
  )
  with_formula = cat == "Debugging" and "Embedded" in data.get(
      "spreadsheet_path", ""
  )

  detail = {"id": data["id"], "category": cat}
  if not os.path.exists(proc_file):
    detail.update({
        "accuracy": 0.0,
        "regression_accuracy": 0.0,
        "modification_accuracy": 0.0,
        "error_message": "output file not exist",
        "cell_errors": [],
        "missing": True,
    })
    return detail

  try:
    need_raw = with_formula
    wb_input = ev.openpyxl.load_workbook(input_file, data_only=not need_raw)
    wb_gt = ev.openpyxl.load_workbook(gt_file, data_only=not need_raw)
    wb_proc = ev.openpyxl.load_workbook(proc_file, data_only=not need_raw)
    if not with_formula:
      wb_input_f = ev.openpyxl.load_workbook(input_file, data_only=False)
      wb_gt_f = ev.openpyxl.load_workbook(gt_file, data_only=False)
      wb_proc_f = ev.openpyxl.load_workbook(proc_file, data_only=False)
    else:
      wb_input_f = wb_gt_f = wb_proc_f = None

    reg = {"correct": 0, "total": 0}
    mod = {"correct": 0, "total": 0}
    msgs = []
    for scr in ev.parse_answer_position(data["answer_position"]):
      if "!" in scr:
        sheet_name, cell_range = scr.split("!")
      else:
        sheet_name, cell_range = wb_gt.sheetnames[0], scr
      sheet_name = sheet_name.strip("'").strip()
      cell_range = cell_range.strip("'").strip()
      rc, mc = ev.classify_cells_by_modification(
          wb_input,
          wb_gt,
          sheet_name,
          cell_range,
          with_font_color,
          with_formula,
          wb_input_formula=wb_input_f,
          wb_answer_formula=wb_gt_f,
      )
      r_c, r_t, m_c, m_t, m_msgs = ev.cell_level_compare_with_classification(
          wb_gt,
          wb_proc,
          sheet_name,
          rc,
          mc,
          with_font_color,
          with_formula,
          wb_answer_formula=wb_gt_f,
          wb_output_formula=wb_proc_f,
      )
      reg["correct"] += r_c
      reg["total"] += r_t
      mod["correct"] += m_c
      mod["total"] += m_t
      msgs.extend([m for m in m_msgs if m])
  except Exception as e:  # noqa: BLE001  an unreadable workbook scores 0, with the reason recorded
    detail.update({
        "accuracy": 0.0,
        "regression_accuracy": 0.0,
        "modification_accuracy": 0.0,
        "error_message": str(e)[:500],
        "cell_errors": [],
    })
    return detail

  reg_ratio = round(reg["correct"] / reg["total"], 4) if reg["total"] else 0.0
  mod_ratio = round(mod["correct"] / mod["total"], 4) if mod["total"] else 0.0
  if reg_ratio >= 0.998:  # official rule
    reg_ratio = 1.0
  acc = 1.0 if reg_ratio == 1.0 and mod_ratio == 1.0 else 0.0
  detail.update({
      "accuracy": acc,
      "regression_accuracy": reg_ratio,
      "modification_accuracy": mod_ratio,
      "regression_cells": reg,
      "modification_cells": mod,
      "error_message": msgs[0] if msgs and not acc else "",
      "cell_errors": msgs[:500],
  })
  return detail


def grade(key: str, deliverables: Path, **_) -> dict:
  cat, tid = key.split("__", 1)
  if cat not in DET_CATS:
    # Visualization needs the VLM checklist path, which is not wrapped. Score None, not 0:
    # a category we cannot measure must be excluded from the average, not counted as a failure
    # on both sides.
    return {
        "score": None,
        "error": f"category {cat} not wrapped (needs VLM checklist path)",
        "grader": "sb2",
    }
  data = _dataset(cat).get(tid)
  if data is None:
    return {"score": 0.0, "error": f"unknown task id {tid}", "grader": "sb2"}
  src = deliverables / f"{tid}_output.xlsx"
  if not src.exists():
    return {
        "score": 0.0,
        "error": f"no {tid}_output.xlsx in deliverables",
        "grader": "sb2",
    }
  with tempfile.TemporaryDirectory(prefix="vh_sb2_", dir="/var/tmp") as td:
    stage = Path(td) / "outputs"
    stage.mkdir()
    shutil.copyfile(src, stage / src.name)
    os.chmod(stage, 0o777)
    os.chmod(stage / src.name, 0o666)
    _recalc(stage)
    det = _grade_det(data, cat, stage)
  return {
      "score": float(det.get("accuracy") or 0.0),
      "detail": det,
      "grader": GRADER,
  }
