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

#!/usr/bin/env python3
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
"""Derive task images that also carry the harness tool stack.

    python3 -m harness.env.derive [--jobs 8] [--only NAME ...]

A benchmark's task image holds the task's own environment and nothing else; the
verifier's skills additionally need the document and data libraries their
scripts
import (openpyxl, python-docx, ...). This builds, for every image named by a
<data>/_worlds/wb/<task>/.exported marker, a derived image `vh/<name>` = the
task
image plus that stack, which env.image_for prefers when it exists. Images whose
Python has no pip are left as they are (the task image is used unchanged).
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys

from harness import config

STACK = (
    "openpyxl xlrd python-docx python-pptx pymupdf pdfplumber pypdf PyPDF2 "
    "pandas numpy scipy statsmodels matplotlib reportlab tabulate pytest"
)
DOCKERFILE = (
    "FROM {base}\nRUN python3 -m pip install --no-cache-dir -q {stack} || pip"
    " install --no-cache-dir -q {stack} || true\n"
)


def derived_name(base: str) -> str:
  return "vh/" + base.split("/")[-1].split(":")[0]


def exists(tag: str) -> bool:
  return (
      subprocess.run(
          ["docker", "image", "inspect", tag], capture_output=True
      ).returncode
      == 0
  )


def build(base: str) -> str:
  tag = derived_name(base)
  if exists(tag):
    return f"{tag}: exists"
  p = subprocess.run(
      ["docker", "build", "-q", "-t", tag, "-"],
      input=DOCKERFILE.format(base=base, stack=STACK),
      capture_output=True,
      text=True,
      timeout=1800,
  )
  return f"{tag}: {'ok' if p.returncode == 0 else 'FAILED ' + p.stderr[-200:]}"


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("--jobs", type=int, default=8)
  ap.add_argument("--only", nargs="*", default=[])
  a = ap.parse_args()
  bases = sorted({
      m.read_text().strip()
      for m in (config.DATA / "_worlds" / "wb").glob("*/.exported")
  })
  if a.only:
    bases = [b for b in bases if b in a.only]
  with ThreadPoolExecutor(a.jobs) as ex:
    for line in ex.map(build, bases):
      print(line, flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
