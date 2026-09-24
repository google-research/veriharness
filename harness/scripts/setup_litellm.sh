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
# One-time setup: project-owned litellm venv for the opus verifier lane.
# Pins: litellm 1.96.0 needs fastapi<=0.128 (0.141 removed get_flat_dependant).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$ROOT/harness/vendor/litellm-venv"

python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q "litellm[proxy]==1.96.0" "fastapi==0.128.0" google-cloud-aiplatform
echo "litellm venv ready at $VENV — start with harness/scripts/litellm_up.sh"
