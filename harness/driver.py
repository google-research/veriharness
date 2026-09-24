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
"""VeriHarness driver: run one verification task through the pi agent runtime.

Four model turns per task, in three sessions:

  resolver      MISSION + INVESTIGATE_ELIM     -> ledger_elim.json
  {disagreements[], notes}
  challenger    MISSION + INVESTIGATE_FALS     -> ledger_fals.json
  {challenges[], notes}
  adjudication  ADJUDICATE, fresh session      -> finish.json       {base |
  "none", work[], open[], notes}
  delivery      REPAIR, adjudication session   -> out/deliverables/ +
  repair.json

The two investigations are independent by construction: separate sessions,
neither
reading the other's record, run concurrently. Every task gets both, because
disputed
and shared errors occur in the same task and land on disjoint claims, so the two
records add up rather than compete.

Selection, revision and reconstruction are one knob, namely how much of the base
survives: all of it (`work` empty), part of it (`work` non-empty), none of it
(base
"none": the artifact is built from the task inputs).

The driver only moves messages and files. It never reads a record's content to
decide
anything. Its one gate is content-blind: the delivered bundle must keep every
file of
its base under the same name (`complete_bundle` restores dropped files
unchanged, then
`validate_delivery` checks the result).
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

from harness import config
from harness import env as env_mod
from harness.views import is_view

JAIL = config.SCRIPTS_DIR / "jail_run.sh"

# The human-authored skill library (paper, Table "The skill library").
DEFAULT_SKILLS = (
    "evidence-xlsx",
    "evidence-pdf",
    "evidence-docx",
    "evidence-pptx",
    "evidence-patch",
    "evidence-bundle",
    "resolve-answer",
    "resolve-workbook",
    "resolve-bundle",
    "falsify-answer",
    "falsify-workbook",
    "falsify-bundle",
    "repair-xlsx",
    "repair-prose",
    "repair-bundle",
    "repair-record",
    "repair-patch",
)

# Output-contract texts substituted into MISSION.md ({{OUTPUT_CONTRACT}}).
CONTRACTS = {
    "pick-only": (
        "pick-only. Your final result must be one of the N rollouts, chosen"
        " as-is; do not produce new artifacts. Deliver your choice via"
        " finish.json."
    ),
    "artifact": (
        "artifact. The result delivered for this task is one rollout's bundle,"
        " corrected and completed in out/ by a later phase from the records"
        " this one leaves. Nothing you write is the deliverable."
    ),
}

# Tool surface per contract. Write access to anything but out/ and the task root is
# removed by the jail, not by the agent runtime.
TOOLS = {
    "pick-only": "read,bash,grep,find,ls",
    "artifact": "read,bash,grep,find,ls,edit,write",
}

# (channel, playbook, record-format doc, record file)
INVESTIGATIONS = (
    ("elim", "INVESTIGATE_ELIM.md", "LEDGER_ELIM.md", "ledger_elim.json"),
    ("fals", "INVESTIGATE_FALS.md", "LEDGER_FALS.md", "ledger_fals.json"),
)

# Operational nudges (recovery only: they add no new instructions).
NUDGE_LEDGER = (
    "You have not written {record} yet. Please write it now, in the LEDGER.md"
    " format, with what you have; then stop."
)
NUDGE_FINISH = (
    "You have not written finish.json yet. Please finish now: write finish.json"
    " as instructed."
)
NUDGE_REPAIR = (
    "You have not written repair.json yet. Please finish the repair phase now:"
    " make sure out/deliverables/ holds the bundle you are delivering, then"
    " write repair.json as instructed."
)

TRANSIENT = (
    "429",
    "Resource exhausted",
    "RESOURCE_EXHAUSTED",
    "overloaded",
    "529",
    "503",
    "UNAVAILABLE",
    "ECONNRESET",
    "ETIMEDOUT",
    "socket hang up",
)
RETRY_BACKOFF = (
    30,
    90,
    180,
)  # seconds; ops-level retry for provider/transport failures only

_LOG_LOCK = threading.Lock()


def log(ws: Path, msg: str) -> None:
  line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
  with _LOG_LOCK:
    print(line, flush=True)
    with open(ws / "driver.log", "a", encoding="utf-8") as f:
      f.write(line + "\n")


def read_json(path: Path):
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return None


def write_json(path: Path, obj) -> None:
  path.write_text(
      json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
  )


def base_of(finish: dict) -> str:
  """The base rollout named by finish.json, normalised to a bare rollout name

  ("rollouts/r08/" -> "r08"); "none" when adjudication found nothing worth
  starting from.
  """
  raw = finish.get("base", finish.get("pick", ""))
  name = str(raw or "").strip().rstrip("/").rsplit("/", 1)[-1]
  return "none" if name.lower() in ("", "none", "null") else name


class Pi:
  """One configured way of running pi turns inside a task workspace."""

  def __init__(
      self,
      ws: Path,
      pi_bin: str,
      flags: list[str],
      use_jail: bool,
      deadline: float,
      native=None,
  ):
    self.ws, self.pi_bin, self.flags = ws, pi_bin, flags
    self.use_jail, self.deadline = use_jail, deadline
    self.native = (
        native  # an env.Native when this turn runs inside the task's own image
    )

  def with_session(self, name: str) -> "Pi":
    """The same configuration with its own session directory (an independent context)."""
    session_dir = self.ws / "session" / name
    session_dir.mkdir(
        parents=True, exist_ok=True
    )  # pi does not create its own session dir
    flags = list(self.flags)
    flags[flags.index("--session-dir") + 1] = str(session_dir)
    return Pi(
        self.ws, self.pi_bin, flags, self.use_jail, self.deadline, self.native
    )

  def in_native(self, native) -> "Pi":
    """The same configuration, run inside the task's own image instead of the jail."""
    return Pi(
        self.ws, self.pi_bin, self.flags, self.use_jail, self.deadline, native
    )

  def _cmd(
      self, message: str, continue_session: bool, env: dict
  ) -> tuple[list[str], str | None]:
    cmd = [self.pi_bin, "-p", *self.flags]
    if continue_session:
      cmd.append("-c")
    cmd += ["--", message]
    if self.native is not None:
      return self.native.wrap(cmd, env)
    return ([str(JAIL), str(self.ws), *cmd] if self.use_jail else cmd), None

  def turn(
      self, message: str, timeout: int, continue_session: bool, tag: str = ""
  ) -> bool:
    """Run one pi turn; True when pi exited cleanly.

    Ops backstops only (no content judgment): the turn is killed as a whole
    process
    group at min(timeout, time left before the task deadline); a turn that dies
    on a
    transient provider/transport error is retried with backoff.
    """
    env = dict(os.environ)
    env.setdefault("PI_CODING_AGENT_DIR", str(config.PI_HOME))
    env.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    env.setdefault("PI_SKIP_VERSION_CHECK", "1")
    env["VERIHARNESS_DATA"] = str(
        config.DATA
    )  # the jail binds data/_worlds read-only
    for attempt in range(len(RETRY_BACKOFF) + 1):
      budget = min(timeout, self.deadline - time.time())
      if budget <= 0:
        log(
            self.ws,
            f"{tag}task deadline reached before turn start; skipping turn",
        )
        return False
      log(
          self.ws,
          f"{tag}pi turn (continue={continue_session}, attempt={attempt + 1},"
          f" budget={int(budget)}s"
          f"{', native ' + self.native.image if self.native else ''})",
      )
      cmd, container = self._cmd(message, continue_session, env)
      proc = subprocess.Popen(
          cmd,
          cwd=self.ws,
          env=env,
          text=True,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.PIPE,
          start_new_session=True,
      )
      try:
        _, err = proc.communicate(timeout=budget)
      except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        if container:
          self.native.kill(container)
        log(
            self.ws,
            f"{tag}pi turn timed out after {int(budget)}s (process group"
            " killed)",
        )
        return False
      log(self.ws, f"{tag}pi exited rc={proc.returncode}")
      if proc.returncode == 0:
        return True
      log(self.ws, f"{tag}pi stderr (tail): {err[-2000:]}")
      if not any(sig in err for sig in TRANSIENT) or attempt == len(
          RETRY_BACKOFF
      ):
        return False
      log(
          self.ws,
          f"{tag}transient provider error; retrying in"
          f" {RETRY_BACKOFF[attempt]}s",
      )
      time.sleep(RETRY_BACKOFF[attempt])
      # A failed first turn may have left a partial session behind; the retry
      # continues it so the model keeps whatever it already read.
      continue_session = True
    return False

  def turn_until(
      self,
      message: str,
      nudge: str,
      output: Path,
      timeouts: tuple[int, int],
      continue_session: bool,
      tag: str = "",
  ):
    """Run a turn that must leave `output` (a JSON file); nudge once if it did not."""
    self.turn(message, timeouts[0], continue_session, tag)
    result = read_json(output)
    if result is None:
      self.turn(nudge, timeouts[1], True, tag)
      result = read_json(output)
    return result


# ----------------------------------------------------------------------------- skills
def _frontmatter(text: str) -> tuple[dict, str]:
  """Split a SKILL.md into its `key: value` frontmatter and its body."""
  if not text.startswith("---"):
    return {}, text
  end = text.find("\n---", 3)
  if end == -1:
    return {}, text
  fields = dict(re.findall(r"^([\w-]+):\s*(.+?)\s*$", text[3:end], re.M))
  return fields, text[end + 4 :].lstrip("\n")


def _globs(value: str | None) -> list[str]:
  return [g.strip().strip("\"'") for g in (value or "").split(",") if g.strip()]


def render_skills(skill_paths, ws: Path, phase: str) -> str:
  """The full text of every skill that applies to this task and this phase, the way pi's

  /skill:name expands it: a header and a per-skill location line, no
  instructions of ours.

  Mounting is a file-name match, not a judgment. `applies-to: <glob>, ...`
  mounts a skill
  only when some rollout delivered a matching file; `phase: <name>, ...` (elim /
  fals /
  adjudicate / repair) restricts it to those turns. Skills with neither always
  mount.
  """
  delivered = {
      p.name
      for p in (ws / "rollouts").glob("*/deliverables/**/*")
      if p.is_file()
  }
  parts = []
  for sp in skill_paths:
    d = Path(sp)
    f = d / "SKILL.md" if d.is_dir() else d
    if not f.exists():
      continue
    fields, body = _frontmatter(f.read_text(encoding="utf-8"))
    phases, applies = _globs(fields.get("phase")), _globs(
        fields.get("applies-to")
    )
    if phases and phase not in phases:
      continue
    if applies and not any(
        fnmatch.fnmatch(n, g) for n in delivered for g in applies
    ):
      continue
    parts.append(
        f"## {d.name if d.is_dir() else f.stem}\n\nSkill directory:"
        f" {f.parent.resolve()}\n\n{body.rstrip()}\n"
    )
  if not parts:
    return ""
  return (
      "\n\n# Evidence instruments\n\nThe skills listed in your system prompt,"
      " in full. Relative paths in them resolve against the skill directory"
      " given for each.\n\n"
      + "\n".join(parts)
  )


# ----------------------------------------------------------------------------- delivery gate
def _bundle_files(root: Path) -> set[str]:
  # Rendered views are the harness's own, never part of a deliverable.
  return {
      p.relative_to(root).as_posix()
      for p in root.rglob("*")
      if p.is_file() and not is_view(p.name)
  }


def validate_delivery(ws: Path, base: str) -> dict:
  """Content-blind contract check: out/deliverables must hold every file of the base

  rollout's bundle under the same name (hence the same format); extra files are
  allowed.
  Not a judgment: it only ensures that what gets graded is a real, complete
  bundle.
  """
  out = ws / "out" / "deliverables"
  if not out.is_dir():
    return {"valid": False, "reason": "out/deliverables missing"}
  have = _bundle_files(out)
  if (
      base == "none"
  ):  # built from the inputs: the only contract is that something was delivered
    nonempty = sorted(f for f in have if (out / f).stat().st_size > 0)
    if not nonempty:
      return {
          "valid": False,
          "reason": "base none and out/deliverables empty",
          "n_base": 0,
          "n_out": 0,
      }
    return {
        "valid": True,
        "n_base": 0,
        "n_out": len(nonempty),
        "added": nonempty[:20],
    }
  base_dir = ws / "rollouts" / base / "deliverables"
  if not base_dir.is_dir():
    return {
        "valid": False,
        "reason": (
            f"base rollout '{base}' has no deliverables dir (base must be a"
            " rollout name)"
        ),
    }
  need = _bundle_files(base_dir)
  missing = sorted(need - have)
  # Empty only counts as a defect when the base's own file had content: a rollout that
  # delivered a zero-byte file is faithfully copied, and failing the bundle for that would
  # punish the copy rather than the rollout.
  empty = sorted(
      f
      for f in need & have
      if (out / f).stat().st_size == 0 and (base_dir / f).stat().st_size > 0
  )
  if missing or empty:
    return {
        "valid": False,
        "reason": f"missing {missing[:5]} empty {empty[:5]}",
        "n_base": len(need),
        "n_out": len(have),
    }
  return {
      "valid": True,
      "n_base": len(need),
      "n_out": len(have),
      "added": sorted(have - need)[:20],
  }


def complete_bundle(ws: Path, base: str) -> list[str]:
  """Copy into out/deliverables every base file the delivery dropped or emptied, unchanged.

  Mechanical and content-blind: a revision that tidied away a file the base had
  delivered would otherwise fail the bundle contract and be discarded whole,
  edits included.
  """
  out, base_dir = (
      ws / "out" / "deliverables",
      ws / "rollouts" / base / "deliverables",
  )
  if base == "none" or not base_dir.is_dir():
    return []
  restored = []
  for rel in sorted(_bundle_files(base_dir)):
    src, dst = base_dir / rel, out / rel
    if not dst.is_file() or (
        dst.stat().st_size == 0 and src.stat().st_size > 0
    ):
      dst.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(src, dst)
      restored.append(rel)
  return restored


def changed_files(ws: Path, base: str) -> list[str]:
  """Files of the delivered bundle whose bytes differ from the base's, plus files it added.

  A record for analysis only: the model's own `applied` flag is not a reliable
  account of whether anything changed.
  """
  out, base_dir = (
      ws / "out" / "deliverables",
      ws / "rollouts" / base / "deliverables",
  )
  if not out.is_dir():
    return []
  digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
  return sorted(
      rel
      for rel in _bundle_files(out)
      if not (base_dir / rel).is_file()
      or digest(out / rel) != digest(base_dir / rel)
  )


# ----------------------------------------------------------------------------- phases
def investigate(
    pi: Pi, args, mission: str, skills: list[str], spec: tuple
) -> bool:
  """One investigation in its own session.

  Each channel gets its record-format doc under its own directory, and the
  playbook points at that path: sharing one file name in the task root let a
  challenger session read the resolver's schema and emit the wrong record.
  """
  name, playbook, ledger_doc, record = spec
  ws = pi.ws
  (ws / name).mkdir(exist_ok=True)
  (ws / name / "LEDGER.md").write_text(
      (config.PROMPTS_DIR / ledger_doc).read_text(encoding="utf-8"),
      encoding="utf-8",
  )
  message = (
      mission
      + "\n\n"
      + (config.PROMPTS_DIR / playbook).read_text(encoding="utf-8")
      + render_skills(skills, ws, name)
  )
  tag = f"[{name}] "
  log(ws, f"{tag}investigation: {playbook}")
  ledger = pi.with_session(name).turn_until(
      message,
      NUDGE_LEDGER.format(record=record),
      ws / record,
      (args.turn_timeout, args.nudge_timeout),
      False,
      tag,
  )
  if ledger is None:
    log(ws, f"{tag}no {record} after nudge")
    return False
  log(
      ws,
      f"{tag}{record}: disagreements={len(ledger.get('disagreements') or [])} "
      f"challenges={len(ledger.get('challenges') or [])}",
  )
  return True


def adjudicate(pi: Pi, args, skills: list[str]):
  """A fresh session that reads both records and inherits neither investigator's context."""
  log(pi.ws, "adjudication: ADJUDICATE.md (fresh session)")
  message = (config.PROMPTS_DIR / "ADJUDICATE.md").read_text(
      encoding="utf-8"
  ) + render_skills(skills, pi.ws, "adjudicate")
  return pi.turn_until(
      message,
      NUDGE_FINISH,
      pi.ws / "finish.json",
      (args.turn_timeout, args.nudge_timeout),
      False,
  )


def deliver(pi: Pi, args, finish: dict, skills: list[str]) -> None:
  """Delivery, in the adjudication session so the decision and both records are in context.

  One text for every task: REPAIR.md executes the revision plan in finish.json.
  Start from the base (or from the inputs when the base is none), do the work,
  deliver the open forks.
  """
  ws, base = pi.ws, base_of(finish)
  base_line = (
      f"\n\nThe adjudication named `{base}` as the base.\n"
      if base != "none"
      else (
          "\n\nThe adjudication found no candidate worth starting from (base"
          " none): build the deliverable from the inputs.\n"
      )
  )
  message = (
      (config.PROMPTS_DIR / "REPAIR.md").read_text(encoding="utf-8")
      + base_line
      + render_skills(skills, ws, "repair")
  )
  (ws / "out" / "deliverables").mkdir(parents=True, exist_ok=True)
  log(ws, "delivery: REPAIR.md (continuing adjudication session)")
  repair = pi.turn_until(
      message,
      NUDGE_REPAIR,
      ws / "repair.json",
      (args.turn_timeout, args.nudge_timeout),
      True,
  )
  restored = complete_bundle(ws, base)
  finish["repair"] = {
      "written": repair is not None,
      **validate_delivery(ws, base),
      "restored": restored[:20],
      "changed": changed_files(ws, base)[:50],
      "applied": bool((repair or {}).get("applied")),
      "changes": (repair or {}).get("changes"),
  }
  write_json(ws / "finish.json", finish)
  log(ws, f"repair: {json.dumps(finish['repair'], ensure_ascii=False)[:600]}")


def resolve_skills(names) -> list[str]:
  """Bare names refer to the built-in library; anything with a path separator is used as given."""
  return [
      str((config.SKILLS_DIR / s).resolve()) if "/" not in s else s
      for s in names
  ]


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(
      description="Run VeriHarness on one materialized task workspace"
  )
  ap.add_argument(
      "ws",
      help="task workspace directory (spec/, workspace/, rollouts/ present)",
  )
  ap.add_argument(
      "--contract",
      choices=list(CONTRACTS),
      default="artifact",
      help=(
          "artifact: select a base and revise it (default); pick-only:"
          " selection only"
      ),
  )
  ap.add_argument("--provider", help="pi --provider value")
  ap.add_argument("--model", help="pi --model value")
  ap.add_argument("--thinking", help="pi --thinking level")
  ap.add_argument(
      "--skill",
      action="append",
      default=None,
      help=(
          "skill name or directory (repeatable; default: the built-in library)"
      ),
  )
  ap.add_argument(
      "--no-skills", action="store_true", help="run with an empty skill library"
  )
  ap.add_argument(
      "--pi-bin", default=str(config.PI_BIN), help="path to the pi executable"
  )
  ap.add_argument(
      "--no-jail",
      action="store_true",
      help="run without the mount-namespace jail (debug only)",
  )
  ap.add_argument(
      "--env",
      choices=["jail", "native", "native-full"],
      default="jail",
      help=(
          "where the turns run: the host jail (default); `native` runs"
          " adjudication and delivery in a fresh container of the task's own"
          " image (see harness/env); `native-full` runs the two investigations"
          " there as well"
      ),
  )
  ap.add_argument(
      "--turn-timeout",
      type=int,
      default=1800,
      help="wall-clock timeout per main turn, seconds",
  )
  ap.add_argument(
      "--nudge-timeout",
      type=int,
      default=600,
      help="wall-clock timeout per nudge turn, seconds",
  )
  ap.add_argument(
      "--task-timeout",
      type=int,
      default=3600,
      help="wall-clock cap for the whole task, seconds",
  )
  args = ap.parse_args(argv)

  ws = Path(args.ws).resolve()
  if not (ws / "rollouts").is_dir():
    print(f"error: {ws / 'rollouts'} not found", file=sys.stderr)
    return 2
  n_rollouts = sum(1 for p in (ws / "rollouts").iterdir() if p.is_dir())
  (ws / "out").mkdir(exist_ok=True)
  skills = (
      [] if args.no_skills else resolve_skills(args.skill or DEFAULT_SKILLS)
  )

  charter = (config.PROMPTS_DIR / "CHARTER.md").read_text(encoding="utf-8")
  mission = (
      (config.PROMPTS_DIR / "MISSION.md")
      .read_text(encoding="utf-8")
      .replace("{{N}}", str(n_rollouts))
      .replace("{{OUTPUT_CONTRACT}}", CONTRACTS[args.contract])
  )
  (ws / "MISSION.md").write_text(mission, encoding="utf-8")

  flags = [
      "--no-context-files",
      "--no-extensions",
      "--no-prompt-templates",
      "--no-skills",
      "--tools",
      TOOLS[args.contract],
      "--session-dir",
      str(ws / "session"),
      "--system-prompt",
      charter,
  ]
  for skill in skills:
    flags += ["--skill", skill]
  for opt in ("provider", "model", "thinking"):
    if getattr(args, opt):
      flags += [f"--{opt}", getattr(args, opt)]

  log(
      ws,
      f"task={ws.name} N={n_rollouts} contract={args.contract}"
      f" skills={len(skills)} "
      f"timeouts(turn/nudge/task)={args.turn_timeout}/{args.nudge_timeout}/{args.task_timeout}s",
  )
  pi = Pi(
      ws, args.pi_bin, flags, not args.no_jail, time.time() + args.task_timeout
  )

  native = env_mod.image_for(ws) if args.env != "jail" else None
  if args.env != "jail" and not native:
    log(ws, "no native image for this task; every turn stays in the jail")
  investigator = (
      pi.in_native(env_mod.Native(ws, native))
      if (native and args.env == "native-full")
      else pi
  )
  if investigator is not pi:
    log(ws, f"native environment for the investigations: {native}")
  with ThreadPoolExecutor(max_workers=len(INVESTIGATIONS)) as ex:
    ok = list(
        ex.map(
            lambda spec: investigate(investigator, args, mission, skills, spec),
            INVESTIGATIONS,
        )
    )
  if not all(ok):
    log(ws, "an investigation left no record; recording no-output")
    return 1

  if native:
    log(ws, f"native environment for adjudication and delivery: {native}")
    pi = pi.in_native(env_mod.Native(ws, native))
  finish = adjudicate(pi, args, skills)
  if finish is None:
    log(ws, "no finish.json after nudge; recording no-output")
    return 1
  log(
      ws,
      f"finish: base={base_of(finish)} work={len(finish.get('work') or [])}"
      f" open={len(finish.get('open') or [])}",
  )

  if args.contract == "artifact":
    deliver(pi, args, finish, skills)
  return 0


if __name__ == "__main__":
  sys.exit(main())
