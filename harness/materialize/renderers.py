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
"""Trajectory renderers, one per archived trajectory format.

Each renderer turns one benchmark's archived trajectory format into plain text
for `rollouts/<r>/trajectory/trajectory.txt`. They drop only provider-opaque
blobs (thought signatures, provider_specific_fields); no message, tool call,
tool output or reasoning text is dropped. Hard-won specifics preserved:

  * WorkBuddy ATIF drops tool RESULTS in conversion; they are rejoined from the
    raw CLI event stream by tool_use_id (`wb_tool_results`).
  * SB-2 `.traj` files are rendered from `history`, never `trajectory` (which
    re-serializes the whole conversation per step — quadratic, 15 MB median).
"""

import json
from pathlib import Path

_OPAQUE = {
    "provider_specific_fields",
    "thought_signature",
    "thinking_blocks",
    "images",
    "signature",
}


def _strip(obj, opaque=_OPAQUE):
  if isinstance(obj, dict):
    return {k: _strip(v, opaque) for k, v in obj.items() if k not in opaque}
  if isinstance(obj, list):
    return [_strip(x, opaque) for x in obj]
  return obj


def _as_text(v, opaque=_OPAQUE) -> str:
  if v is None:
    return ""
  if isinstance(v, str):
    return v
  return json.dumps(_strip(v, opaque), ensure_ascii=False)


# ------------------------------------------------------------- APEX / OpenAI
def render_openai_messages(messages: list) -> str:
  out = []
  for m in messages:
    role = m.get("role", "?")
    if role == "system":
      continue
    parts = []
    if m.get("reasoning_content"):
      parts.append(f"[thinking]\n{_as_text(m['reasoning_content'])}")
    c = m.get("content")
    if c:
      parts.append(_as_text(c))
    for tc in m.get("tool_calls") or []:
      fn = tc.get("function") or {}
      parts.append(
          f"[tool_call {fn.get('name')}]\n{_as_text(fn.get('arguments'))}"
      )
    if m.get("name") and role == "tool":
      parts.insert(0, f"[tool_result {m['name']}]")
    if parts:
      out.append(f"<{role}>\n" + "\n".join(parts))
  return "\n\n".join(out)


# ---------------------------------------------------------- JobBench/OpenCode
def render_opencode_events(lines: list) -> str:
  out = []
  for line in lines:
    try:
      e = json.loads(line)
    except Exception:  # noqa: BLE001 — a corrupt line is skipped
      continue
    t, part = e.get("type"), (e.get("part") or {})
    if t == "tool_use":
      st = part.get("state") or {}
      out.append(
          f"<tool {part.get('tool')}>\ninput: {_as_text(st.get('input'))}"
          f"\noutput: {_as_text(st.get('output'))}"
      )
    elif t in ("text", "message", "assistant_text"):
      txt = _as_text(part.get("text") or part.get("content"))
      if txt.strip():
        out.append(f"<assistant>\n{txt}")
    elif t == "reasoning":
      txt = _as_text(part.get("text"))
      if txt.strip():
        out.append(f"<thinking>\n{txt}")
  return "\n\n".join(out)


# ------------------------------------------------------------ WorkBuddy/ATIF
def wb_tool_results(run_dir: Path) -> dict:
  """Rejoin tool OUTPUTS that WorkBuddy's ATIF conversion drops, from the raw

  CLI event stream (cbc-output.txt / cc-output.txt), keyed by tool_use_id.
  """
  for name in ("cbc-output.txt", "cc-output.txt"):
    raw = run_dir / "agent" / name
    if raw.exists():
      break
  else:
    return {}
  out = {}
  for line in raw.read_text(errors="replace").splitlines():
    if '"tool_result"' not in line:
      continue
    try:
      ev = json.loads(line)
    except Exception:  # noqa: BLE001
      continue
    msg = ev.get("message")
    if not isinstance(msg, dict):
      continue
    for b in msg.get("content") or []:
      if isinstance(b, dict) and b.get("type") == "tool_result":
        tid = b.get("tool_use_id")
        if not tid:
          continue
        c = b.get("content")
        if isinstance(c, list):
          txt = "\n".join(
              x.get("text", "")
              for x in c
              if isinstance(x, dict) and x.get("type") == "text"
          )
          c = txt or c
        out[tid] = _as_text(c)
        if b.get("is_error"):
          out[tid] = "[tool reported an error]\n" + out[tid]
  return out


def render_atif_steps(traj, results=None) -> str:
  steps = traj.get("steps") if isinstance(traj, dict) else traj
  results = results or {}
  out = []
  for st in steps or []:
    if not isinstance(st, dict):
      continue
    parts = []
    if st.get("thinking"):
      parts.append(f"[thinking]\n{_as_text(st['thinking'])}")
    if st.get("message"):
      parts.append(_as_text(st["message"]))
    for tc in st.get("tool_calls") or []:
      nm = (
          tc.get("tool_name")
          or tc.get("name")
          or tc.get("function_name")
          or (tc.get("function") or {}).get("name")
      )
      args = (
          tc.get("arguments")
          or tc.get("input")
          or (tc.get("function") or {}).get("arguments")
      )
      parts.append(f"[tool_call {nm}]\n{_as_text(args)}")
      if tc.get("result") is not None or tc.get("output") is not None:
        parts.append(
            "[tool_result"
            f" {nm}]\n{_as_text(tc.get('result', tc.get('output')))}"
        )
      elif tc.get("tool_call_id") in results:
        parts.append(f"[tool_result {nm}]\n{results[tc['tool_call_id']]}")
    for tr in st.get("tool_results") or []:
      parts.append(f"[tool_result]\n{_as_text(tr)}")
    if parts:
      out.append(
          f"<{st.get('source', 'step')} {st.get('step_id', '')}>\n"
          + "\n".join(parts)
      )
  return "\n\n".join(out)


# ------------------------------------------------------------------ WSB
def render_wsb_traj(f: Path) -> str:
  try:
    tr = json.loads(f.read_text(errors="replace")).get("trace") or {}
  except Exception as e:  # noqa: BLE001
    return f"(trajectory unreadable: {type(e).__name__}: {e})"
  out = []
  for st in tr.get("executionTrace") or []:
    if not isinstance(st, dict):
      continue
    if st.get("type") == "tool":
      head = f"[tool_call {st.get('tool')}]\n{_as_text(st.get('input'))}"
      status = f"status={st.get('status')} exitCode={st.get('exitCode')}"
      out.append(
          f"<tool>\n{head}\n[tool_result {st.get('tool')}] {status}\n"
          f"{_as_text(st.get('output'))}"
      )
    else:
      c = _as_text(st.get("content"))
      if c.strip():
        out.append(f"<{st.get('role', 'assistant')}>\n{c}")
  return "\n\n".join(out)


# ------------------------------------------------------- SB-2 / SWE-agent
_SB2_OPAQUE = _OPAQUE | {"tool_calls"}  # flash bakes signatures into tool-call
# ids; tool_calls is a second copy of the
# arguments already rendered via `action`


def render_sb2_traj(f: Path) -> str:
  """Render a SWE-agent .traj from `history`, never `trajectory` (quadratic)."""
  try:
    h = json.loads(f.read_text(errors="replace")).get("history") or []
  except Exception as e:  # noqa: BLE001
    return f"(trajectory unreadable: {type(e).__name__}: {e})"
  out = []
  for m in h:
    role = m.get("role", "?")
    if m.get("message_type") == "system_prompt":
      continue
    parts = []
    if m.get("thought"):
      parts.append(f"[thinking]\n{_as_text(m['thought'], _SB2_OPAQUE)}")
    if m.get("action"):
      parts.append(f"[action]\n{_as_text(m['action'], _SB2_OPAQUE)}")
    c = m.get("content")
    if c:
      parts.append(_as_text(c, _SB2_OPAQUE))
    if parts:
      out.append(f"<{role}>\n" + "\n".join(parts))
  return "\n\n".join(out)


CELLS_TSV_CAP = 200_000  # lines; beyond this the sheet is cut with a marker (huge data dumps)


def render_cells_tsv(xlsx_path, out_path) -> bool:
  """Sibling view of a workbook: one line per non-empty cell, `Sheet!A1<TAB>value<TAB>formula`,

  plus `<TAB># comment` where the cell carries a note (notes often state the
  convention a
  template expects, and are invisible in a dump of values). Cached values
  (data_only) next
  to formulas; formulas empty for literals. Lets a single grep compare one cell
  across every
  rollout and the input. Returns False if unreadable.
  """
  import openpyxl

  try:
    wbf = openpyxl.load_workbook(xlsx_path, data_only=False, read_only=False)
    wbv = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=False)
  except Exception:  # noqa: BLE001
    return False
  n = 0
  with open(out_path, "w", encoding="utf-8") as out:
    for ws in wbf.worksheets:
      wsv = wbv[ws.title]
      for row in ws.iter_rows():
        for c in row:
          note = (
              ("\t# " + " ".join(str(c.comment.text).split()))
              if c.comment is not None
              else ""
          )
          if c.value is None and not note:
            continue
          v = "" if c.value is None else c.value
          if isinstance(v, str) and v.startswith("="):
            cached = wsv[c.coordinate].value
            out.write(
                f"{ws.title}!{c.coordinate}\t{'' if cached is None else cached}\t{v}{note}\n"
            )
          else:
            out.write(f"{ws.title}!{c.coordinate}\t{v}\t{note}\n")
          n += 1
          if n >= CELLS_TSV_CAP:
            out.write(f"# cut at {CELLS_TSV_CAP} cells\n")
            return True
  return True
