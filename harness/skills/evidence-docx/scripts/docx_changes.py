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

"""Tracked changes and comments of a .docx, read from the OOXML parts.

usage: docx_changes.py FILE

Prints insertions/deletions (author, date, text) in document order, then
comments (author, date, anchored text, comment text).
"""

import sys
import xml.etree.ElementTree as ET
import zipfile

if len(sys.argv) != 2:
  sys.exit(__doc__)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
z = zipfile.ZipFile(sys.argv[1])
doc = ET.fromstring(z.read("word/document.xml"))


def text_of(el):
  return "".join(
      t.text or "" for t in el.iter() if t.tag in (W + "t", W + "delText")
  )


n = 0
for el in doc.iter():
  if el.tag in (W + "ins", W + "del"):
    kind = "INS" if el.tag == W + "ins" else "DEL"
    print(
        f"{kind} [{el.get(W + 'author')}, {el.get(W + 'date')}] {text_of(el)!r}"
    )
    n += 1
print(f"# {n} tracked changes")

if "word/comments.xml" in z.namelist():
  com = ET.fromstring(z.read("word/comments.xml"))
  anchors = {}
  current = None
  for el in doc.iter():
    if el.tag == W + "commentRangeStart":
      current = el.get(W + "id")
      anchors[current] = []
    elif el.tag == W + "commentRangeEnd":
      current = None
    elif current is not None and el.tag == W + "t":
      anchors[current].append(el.text or "")
  m = 0
  for c in com.findall(W + "comment"):
    cid = c.get(W + "id")
    print(
        f"COMMENT {cid} [{c.get(W + 'author')}, {c.get(W + 'date')}] on"
        f" {''.join(anchors.get(cid, []))!r}: {text_of(c)!r}"
    )
    m += 1
  print(f"# {m} comments")
else:
  print("# 0 comments (no comments part)")
