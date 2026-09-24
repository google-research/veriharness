#!/usr/bin/env python3
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

"""bundle_inventory: across all candidates, who delivered what.

  bundle_inventory.py ROLLOUTS_DIR [--base rNN] [--min-len 4] [--max 60]

Reads each candidate's deliverables through the pre-rendered views (.text.txt,
.cells.tsv) and
plain-text files. Prints the files per candidate, headings not shared by all,
and the specifics
(figures, identifiers, dates) grouped by how many candidates state them, with
file and line.
With --base, only what other candidates state and the base does not. Reads only;
writes nothing.
"""

import argparse, re, sys
from collections import defaultdict
from pathlib import Path

TEXT_EXT = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".html",
    ".htm",
    ".xml",
    ".yaml",
    ".yml",
}
SPECIFIC = re.compile(
    r"""
    \b\d{4}-\d{2}-\d{2}\b                       # ISO date
  | \b[A-Z]{2,}[-_/]?\d[\w-]*\b                 # identifier: INV-2031, PO12345, SKU_77A
  | (?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?      # 1,234,567.89
  | (?<![\w.])\d+\.\d+%?                        # 12.5  3.75%
  | (?<![\w.])\d{3,}%?(?![\w])                  # 440051
""",
    re.X,
)


def norm(tok: str) -> str:
  t = tok.replace(",", "")
  if re.fullmatch(r"\d+\.\d+%?", t):
    pct = t.endswith("%")
    t = t.rstrip("%").rstrip("0").rstrip(".") + ("%" if pct else "")
  return t


def read_bundle(deliv: Path):
  """-> (files {rel: bytes}, lines [(rel, text)]) using views for binary documents."""
  files, lines = {}, []
  for p in sorted(deliv.rglob("*")):
    if not p.is_file():
      continue
    rel = p.relative_to(deliv).as_posix()
    view = rel.endswith((".text.txt", ".cells.tsv"))
    if not view:
      files[rel] = p.stat().st_size
    if view or p.suffix.lower() in TEXT_EXT:
      src = rel.rsplit(".", 2)[0] if view else rel
      try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
          if ln.strip():
            lines.append((src, ln.strip()))
      except OSError:
        pass
  return files, lines


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("rollouts")
  ap.add_argument(
      "--base",
      help="list only what other candidates state and this one does not",
  )
  ap.add_argument(
      "--min-len", type=int, default=4, help="shortest specific worth listing"
  )
  ap.add_argument("--max", type=int, default=60, help="rows per section")
  a = ap.parse_args()
  cands = sorted(
      d.name
      for d in Path(a.rollouts).iterdir()
      if (d / "deliverables").is_dir()
  )
  if not cands:
    print("no candidates with deliverables/ found", file=sys.stderr)
    return 1
  files, heads, specs = (
      {},
      defaultdict(set),
      defaultdict(dict),
  )  # specs[token][cand] = (file, line)
  for c in cands:
    files[c], lines = read_bundle(Path(a.rollouts) / c / "deliverables")
    for src, ln in lines:
      if ln.startswith("#") and len(ln) < 120:
        heads[re.sub(r"[^a-z0-9 ]", "", ln.lower()).strip()].add(c)
      for m in SPECIFIC.finditer(ln):
        tok = norm(m.group(0))
        if len(tok) >= a.min_len:
          specs[tok].setdefault(c, (src, ln[:160]))
  n = len(cands)
  print(f"# files ({n} candidates)")
  for c in cands:
    print(f"{c}: " + ", ".join(f"{f} ({s:,}B)" for f, s in files[c].items()))
  names = defaultdict(set)
  for c in cands:
    for f in files[c]:
      names[f].add(c)
  partial = {f: cs for f, cs in names.items() if len(cs) < n}
  if partial:
    print("\n# files not delivered by everyone")
    for f, cs in sorted(partial.items(), key=lambda kv: -len(kv[1])):
      print(f"{f}: {' '.join(sorted(cs))}")

  def wanted(holders):
    return 0 < len(holders) < n and (not a.base or a.base not in holders)

  rows = [(h, cs) for h, cs in heads.items() if h and wanted(cs)]
  if rows:
    print(
        "\n# headings not shared by all"
        + (f" (absent from {a.base})" if a.base else "")
    )
    for h, cs in sorted(rows, key=lambda kv: -len(kv[1]))[: a.max]:
      print(f"[{len(cs)}/{n}] {h}  <- {' '.join(sorted(cs))}")
  rows = [(t, hs) for t, hs in specs.items() if wanted(hs)]
  print(
      "\n# specifics not shared by all"
      + (f" (absent from {a.base})" if a.base else "")
      + f": {len(rows)} (showing {min(len(rows), a.max)}; most widely held"
      " first)"
  )
  for tok, hs in sorted(rows, key=lambda kv: (-len(kv[1]), kv[0]))[: a.max]:
    c0 = sorted(hs)[0]
    src, ln = hs[c0]
    print(
        f"[{len(hs)}/{n}] {tok}  <- {' '.join(sorted(hs))}\n        {c0}:{src}:"
        f" {ln}"
    )
  return 0


if __name__ == "__main__":
  sys.exit(main())
