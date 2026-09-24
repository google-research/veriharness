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
"""Filesystem locations and verifier model lanes.

Everything host-specific is read from the environment so the code carries no
machine paths, cloud project names or credentials:

    VERIHARNESS_DATA        materialized rollout pools        (default:
    <repo>/data)
    VERIHARNESS_RUNS        run outputs                       (default:
    <repo>/runs)
    VERIHARNESS_BENCH_ROOT  checkout holding the upstream benchmarks and their
    archived
                            rollouts; needed only to materialize pools and to
                            re-grade
                            revised artifacts (layout: see README, "Benchmarks")
"""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS_DIR = REPO / "harness"
PROMPTS_DIR = HARNESS_DIR / "prompts"
SKILLS_DIR = HARNESS_DIR / "skills"
SCRIPTS_DIR = HARNESS_DIR / "scripts"


def _path(var: str, default: Path) -> Path:
  return Path(os.environ.get(var) or default).expanduser().resolve()


DATA = _path("VERIHARNESS_DATA", REPO / "data")
RUNS = _path("VERIHARNESS_RUNS", REPO / "runs")
# The pi agent runtime and its config live inside the harness directory because the jail
# exposes exactly these two paths to the verifier (scripts/setup_pi.sh installs pi).
PI_BIN = HARNESS_DIR / "vendor" / "node_modules" / ".bin" / "pi"
PI_HOME = HARNESS_DIR / "pi-home"

BENCHES = ("apex", "wsb", "wb", "sb2", "jb")

# A lane is the verifier model. By default a pool is verified by the model that
# generated it (the same-model setting), so lanes and pools share names.
LANES = {
    "flash": [
        "--provider",
        "google-vertex",
        "--model",
        "gemini-3.5-flash",
        "--thinking",
        "high",
    ],
    "opus": [
        "--provider",
        "vertex-litellm",
        "--model",
        "claude-opus-4-8",
        "--thinking",
        "high",
    ],
}
# Lanes served through the local litellm proxy (scripts/litellm_up.sh).
PROXIED_LANES = ("opus",)


def bench_root() -> Path:
  """The upstream benchmark checkout.

  Raises with instructions when unset, so that a missing grader never degrades
  into silent zeros.
  """
  root = os.environ.get("VERIHARNESS_BENCH_ROOT")
  if not root:
    raise RuntimeError(
        "VERIHARNESS_BENCH_ROOT is not set: point it at the directory that"
        " holds benchmarks/<name>/ (see README, 'Benchmarks')."
    )
  return Path(root).expanduser().resolve()
