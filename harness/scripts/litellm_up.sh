#!/usr/bin/env bash
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
# Start (or report) the project-owned litellm proxy for the opus verifier lane.
# Idempotent: if something already answers on the port, leave it alone.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$ROOT/harness/vendor/litellm-venv"
CFG="$ROOT/harness/scripts/litellm.yaml"
PORT=4180
: "${VERTEX_PROJECT:?set VERTEX_PROJECT to your Google Cloud project}"
export VERTEX_LOCATION="${VERTEX_LOCATION:-global}"
LOG="$ROOT/harness/vendor/litellm.log"
PIDFILE="$ROOT/harness/vendor/litellm.pid"

if curl -sf -o /dev/null "http://127.0.0.1:$PORT/health/liveliness"; then
  echo "litellm already up on :$PORT"
  exit 0
fi

nohup "$VENV/bin/litellm" --config "$CFG" --port "$PORT" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"

for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/health/liveliness"; then
    echo "litellm up on :$PORT (pid $(cat "$PIDFILE"), log $LOG)"
    exit 0
  fi
  sleep 1
done
echo "litellm failed to come up — see $LOG" >&2
exit 1
