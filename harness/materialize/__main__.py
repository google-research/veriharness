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
"""Materialization CLI: one entry, one adapter per benchmark.

    python3 -m harness.materialize <bench> [--pool P] [--only KEY] [--limit N]

Each adapter maps one benchmark's archive of rollouts into the unified
task-workspace
layout written by base.py. The adapters encode the archive layout our pools were
generated into; to bring your own rollouts, write an adapter that yields
base.Task
objects, or produce the layout documented in base.py directly.
"""

from importlib import import_module
import sys

from harness.config import BENCHES
from harness.materialize.base import run_cli


def main() -> int:
  if len(sys.argv) < 2 or sys.argv[1] not in BENCHES:
    print(
        f"usage: python3 -m harness.materialize <{'|'.join(BENCHES)}> [--pool"
        " P] [--only KEY] [--limit N]",
        file=sys.stderr,
    )
    return 2
  adapter = import_module(f"harness.materialize.{sys.argv[1]}")
  return run_cli(
      sys.argv[1], list(adapter.POOLS), adapter.iter_tasks, sys.argv[2:]
  )


sys.exit(main())
