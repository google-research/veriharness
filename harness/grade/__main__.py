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

"""Grade one deliverables directory:

python3 -m harness.grade <bench> <task_key> <deliverables_dir> [--json]
"""

import argparse
import json
from pathlib import Path
import sys

from harness.config import BENCHES
from harness.grade import grade_deliverables


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
  ap.add_argument("bench", choices=BENCHES)
  ap.add_argument("key")
  ap.add_argument("deliverables")
  ap.add_argument("--json", action="store_true")
  args = ap.parse_args()
  result = grade_deliverables(args.bench, args.key, Path(args.deliverables))
  print(
      json.dumps(result, indent=1, default=str)
      if args.json
      else f"{result.get('score')}  {result.get('error', '')}"
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
