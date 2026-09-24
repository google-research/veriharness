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
"""Re-grading of NEW deliverables (revised or reconstructed bundles) through each

benchmark's own grader.

    from harness.grade import grade_deliverables
    grade_deliverables("sb2", "<task key>", Path("<run>/sb2_opus/<task
    key>/out/deliverables"))
        -> {"score": float in [0, 1] | None, "detail": ..., "grader": "..."}

One module per benchmark; each wraps the upstream entry point without modifying
it
and locates the upstream checkout through VERIHARNESS_BENCH_ROOT. Graders run on
the
host after the verifier batch, never inside the verifier's jail. Scores are on
the
same scale as <data>/<bench>/<pool>/meta.json, so delivered bundles compare with
the archived rollouts directly. A score of None means "could not be graded" and
is
never to be read as zero.
"""

from importlib import import_module
from pathlib import Path

from harness.config import BENCHES


def _module(bench: str):
  if bench not in BENCHES:
    raise ValueError(f"unknown bench {bench!r}")
  return import_module(f"harness.grade.{bench}")


def grade_deliverables(bench: str, key: str, deliverables: Path, **kw) -> dict:
  return _module(bench).grade(key, Path(deliverables), **kw)


def preflight(bench: str) -> str:
  """Empty when the bench's grader is usable, else what is wrong.

  LLM-judge graders fail soft (a dead judge scores everything 0.0), so scoring
  refuses to start without this.
  """
  check = getattr(_module(bench), "preflight", None)
  return check() if check else ""
