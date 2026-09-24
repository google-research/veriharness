#!/usr/bin/env bash
# Copyright 2026 The VeriHarness Authors.
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
#
# Install the upstream benchmarks that harness/grade/<bench>.py wraps, under
# $VERIHARNESS_BENCH_ROOT/benchmarks/. Nothing is copied into this repository: each
# benchmark's code is cloned at a pinned commit, its data fetched from Hugging Face, and
# its environment and images built with its own tooling.
#
#   harness/scripts/setup_benchmarks.sh <apex|wsb|wb|sb2|jb|all> [--no-images]
#
# Needs git, uv, docker and a python3 with huggingface_hub (pip install -r requirements.txt).
# JOBS=N sets how many WorkBuddy task images build at once (default 4). Judge credentials
# are not installed here: the templates copied into place name what to fill in, and the
# README ("Benchmarks and grading") lists the environment variables the graders read.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUPPORT="$REPO/harness/benchmarks"
: "${VERIHARNESS_BENCH_ROOT:?set VERIHARNESS_BENCH_ROOT to the directory that will hold benchmarks/<name>/}"
ROOT="$VERIHARNESS_BENCH_ROOT/benchmarks"
JOBS="${JOBS:-4}"
IMAGES=1

# The upstream commits the paper's runs and these graders were validated against. The APEX
# repository rewrites its history, so it is installed at its current head.
APEX_REPO=https://github.com/Mercor-Intelligence/archipelago
WSB_REPO=https://github.com/OpenDataBox/Workspace-Bench;       WSB_REF=a3a2ee4
WB_REPO=https://github.com/Tencent/workbuddy-bench;            WB_REF=b516950
SB2_REPO=https://github.com/RUCKBReasoning/SpreadsheetBench-2; SB2_REF=5c16026
JB_REPO=https://github.com/Job-Bench/job-bench-eval;           JB_REF=0152c80

clone() {   # url ref dir
  [ -d "$3/.git" ] || git clone --quiet "$1" "$3"
  git -C "$3" checkout --quiet "$2"
}
copy_if_missing() {   # template destination
  [ -e "$2" ] || { cp "$1" "$2"; echo "  wrote $2: fill in the endpoint and credentials"; }
}

apex() {
  local d="$ROOT/apex"
  echo "== apex: Archipelago grading runner (upstream head)"
  [ -d "$d/.git" ] || git clone --quiet "$APEX_REPO" "$d"
  (cd "$d/grading" && uv sync --locked)
  echo "  task prompts and rubrics come from Hugging Face (mercor/apex-agents) on first use"
}

wsb() {
  local d="$ROOT/wsb_lite/official"
  echo "== wsb: Workspace-Bench @ $WSB_REF"
  clone "$WSB_REPO" "$WSB_REF" "$d"
  copy_if_missing "$SUPPORT/wsb/env.example" "$d/evaluation/.env"
  # The Lite split the paper uses, plus the workspace file systems the tasks read.
  (cd "$d/evaluation" && python3 scripts/download_hf_assets.py --lite --workspaces)
  [ -e "$d/evaluation/tasks" ] || ln -s tasks_lite "$d/evaluation/tasks"     # the grader reads tasks/<key>/
  if [ "$IMAGES" = 1 ]; then
    (cd "$d/evaluation" && docker compose -f docker/docker-compose.yaml build &&
     docker compose -f docker/docker-compose.yaml run --rm workspace-bench \
       bash /workspace/Workspace-Bench/evaluation/docker/bootstrap.sh)
  fi
}

wb() {
  local d="$ROOT/workbuddy/workbuddy-bench"
  echo "== wb: WorkBuddy Bench @ $WB_REF"
  clone "$WB_REPO" "$WB_REF" "$d"
  (cd "$d" && uv sync)
  mkdir -p "$d/configs/models/vertex"
  cp "$SUPPORT/wb/models/vertex/gemini-3.5-flash.yaml" "$d/configs/models/vertex/"
  copy_if_missing "$SUPPORT/wb/env.example" "$d/.env"
  (cd "$d" && scripts/dataset/fetch-dataset.sh code office web)
  if [ "$IMAGES" = 1 ]; then
    # Every task ships its own Dockerfile; one image per task, found by the grader and by
    # --env native under the tag <task>__local__env-main.
    echo "  building one image per task, $JOBS at a time"
    find "$d/datasets" -mindepth 4 -maxdepth 4 -type d -name environment -path '*/tasks/*' | sort |
      xargs -P "$JOBS" -I{} bash -c '
        e="{}"; t="$(basename "$(dirname "$e")" | tr "[:upper:]" "[:lower:]")"; tag="${t}__local__env-main"
        if docker image inspect "$tag" >/dev/null 2>&1; then echo "  $tag exists"
        elif docker build -q -t "$tag" "$e" >/dev/null 2>&1; then echo "  $tag ok"
        else echo "  $tag FAILED"; fi'
  fi
}

sb2() {
  local d="$ROOT/sb2/official"
  echo "== sb2: SpreadsheetBench 2 @ $SB2_REF"
  clone "$SB2_REPO" "$SB2_REF" "$d"
  if [ ! -d "$d/data/Debugging" ]; then
    python3 - "$d" <<'PY'
import sys, zipfile
from pathlib import Path
from huggingface_hub import hf_hub_download
d = Path(sys.argv[1]); raw = d / "data_raw"; raw.mkdir(exist_ok=True)
zipfile.ZipFile(hf_hub_download("KAKA22/SpreadsheetBench-v2", "spreadsheetbench-v2.zip", repo_type="dataset")).extractall(raw)
if not (d / "data").exists():
    (d / "data").symlink_to("data_raw/spreadsheetbench-v2")
PY
  fi
  if [ "$IMAGES" = 1 ]; then
    docker image inspect spreadsheetbench-v2 >/dev/null 2>&1 ||
      docker build -f "$d/SWE-agent/spreadsheet.Dockerfile" -t spreadsheetbench-v2 "$d/SWE-agent"
    # The grader runs the official recalculation script, which needs tqdm the image lacks.
    printf 'FROM spreadsheetbench-v2\nRUN pip install --no-cache-dir tqdm\n' | docker build -q -t veriharness-sb2 -
    # The benchmark requires the input and golden workbooks recalculated once before any
    # evaluation; the official script only handles *output.xlsx, so its functions are called
    # directly on every workbook of the dataset. Slow (thousands of files).
    if [ ! -e "$d/data_raw/.recalculated" ]; then
      docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$d:/sb2" veriharness-sb2 python3 -c '
import glob, sys
sys.path.insert(0, "/sb2/evaluation")
import open_spreadsheet as o
files = sorted(glob.glob("/sb2/data_raw/**/*.xlsx", recursive=True))
print(len(files), "workbooks")
assert o.start_libreoffice_service()
try:
    o.batch_open_files(files)
finally:
    o.stop_libreoffice_service()'
      touch "$d/data_raw/.recalculated"
    fi
  fi
}

jb() {
  local d="$ROOT/jobbench/job-bench-eval"
  echo "== jb: JobBench @ $JB_REF"
  clone "$JB_REPO" "$JB_REF" "$d"
  (cd "$d" && ./setup.sh)      # uv sync + the dataset from Hugging Face (JobBench/job-bench)
}

BENCHES=()
for arg in "$@"; do
  case "$arg" in
    --no-images) IMAGES=0 ;;
    apex|wsb|wb|sb2|jb) BENCHES+=("$arg") ;;
    all) BENCHES=(apex wsb wb sb2 jb) ;;
    *) echo "usage: $0 <apex|wsb|wb|sb2|jb|all> [--no-images]" >&2; exit 2 ;;
  esac
done
[ "${#BENCHES[@]}" -gt 0 ] || { echo "usage: $0 <apex|wsb|wb|sb2|jb|all> [--no-images]" >&2; exit 2; }
mkdir -p "$ROOT"
for b in "${BENCHES[@]}"; do "$b"; done
echo "done: $ROOT"
