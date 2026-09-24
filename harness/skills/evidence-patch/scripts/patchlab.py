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

"""patchlab: build one scratch tree per candidate patch and run the same command in each.

  patchlab.py build --base DIR --out LAB  NAME=PATCH [NAME=PATCH ...]
      LAB/_base/            pristine copy of DIR (symlinks resolved), committed
      in a throwaway git repo
      LAB/<NAME>/           copy of _base with PATCH applied (strict ->
      --recount -> --3way -> patch(1) fuzz)
      LAB/build.json        {NAME: {applied, mode, files, rejected,
      skipped_binary, stderr}}
  patchlab.py run --out LAB [--timeout 300] [--jobs 4] [--only NAME,NAME] [--tag
  T] -- CMD...
      runs CMD (a shell string) with cwd = each tree (and _base), in parallel;
      LAB/run_<T>.json      {NAME: {rc, secs, timeout, tail}}; full output in
      LAB/<NAME>.<T>.log
      and prints one line per tree so rows can be compared against _base.
Nothing outside LAB is written. No network, no installs.
"""

import argparse, concurrent.futures as cf, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

JUNK = re.compile(
    r"(^|/)(__pycache__|\.pytest_cache|node_modules|\.git|\.venv|[^/]+\.egg-info)(/|$)|\.pyc$"
)
ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "lab",
    "GIT_AUTHOR_EMAIL": "lab@lab",
    "GIT_COMMITTER_NAME": "lab",
    "GIT_COMMITTER_EMAIL": "lab@lab",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "PIP_NO_INPUT": "1",
    "PYTEST_ADDOPTS": "-p no:randomly -p no:cacheprovider",
}


def sh(cmd, cwd, **kw):
  return subprocess.run(
      cmd,
      cwd=cwd,
      env=ENV,
      capture_output=True,
      text=True,
      errors="replace",
      **kw,
  )


def split_patch(text):
  """-> (replayable text, [paths of dropped sections]).

  Drops binary stubs and cache/dependency paths.
  """
  parts = re.split(r"(?m)^(?=diff --git )", text)
  keep, dropped, files = [], [], []
  for p in parts:
    m = re.match(r"diff --git a/(.*?) b/(.*)", p)
    if not m:
      continue
    path = m.group(2).strip()
    if (
        JUNK.search(path)
        or re.search(r"(?m)^Binary files .* differ$", p)
        and "GIT binary patch" not in p
    ):
      dropped.append(path)
      continue
    keep.append(p)
    files.append(path)
  return "".join(keep), dropped, files


def build_one(lab, name, patch):
  tree = lab / name
  if tree.exists():
    shutil.rmtree(tree)
  shutil.copytree(lab / "_base", tree, symlinks=True)
  info = {
      "applied": False,
      "mode": None,
      "files": [],
      "skipped": [],
      "stderr": "",
  }
  try:
    text = Path(patch).read_text(errors="replace")
  except OSError as e:
    info["stderr"] = str(e)
    return name, info
  body, info["skipped"], info["files"] = split_patch(text)
  if not body.strip():
    info["stderr"] = "empty patch (nothing replayable)"
    return name, info
  pf = lab / f"{name}.clean.patch"
  pf.write_text(body)
  for mode, cmd in (
      ("strict", ["git", "apply", "--whitespace=nowarn"]),
      ("recount", ["git", "apply", "--whitespace=nowarn", "--recount"]),
      ("3way", ["git", "apply", "--whitespace=nowarn", "--recount", "-3"]),
      ("fuzz", ["patch", "-p1", "-s", "-f", "--no-backup-if-mismatch", "-i"]),
  ):
    r = sh(cmd + [str(pf)], tree)
    if r.returncode == 0:
      info.update(applied=True, mode=mode)
      break
    info["stderr"] = (r.stderr or r.stdout)[-600:]
    sh(["git", "checkout", "-q", "--", "."], tree)
    sh(["git", "clean", "-fdq"], tree)
  return name, info


def cmd_build(a):
  lab = Path(a.out).resolve()
  base = lab / "_base"
  if not base.exists():
    lab.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        Path(a.base).resolve(),
        base,
        symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git"),
    )
    sh(["git", "init", "-q"], base)
    sh(["git", "config", "gc.auto", "0"], base)
    sh(["git", "add", "-A", "-f"], base)
    sh(["git", "commit", "-qm", "base", "--allow-empty"], base)
  pairs = [x.split("=", 1) for x in a.cands]
  out = {}
  with cf.ThreadPoolExecutor(a.jobs) as ex:
    for name, info in ex.map(lambda p: build_one(lab, *p), pairs):
      out[name] = info
      print(
          f"{name:8} applied={info['applied']!s:5} mode={info['mode']}"
          f" files={len(info['files'])} "
          f"skipped={len(info['skipped'])}"
          f" {info['stderr'].strip().splitlines()[-1] if not info['applied'] and info['stderr'] else ''}"
      )
  (lab / "build.json").write_text(json.dumps(out, indent=1))


def run_one(lab, name, cmd, timeout, tag):
  t0 = time.time()
  log = lab / f"{name}.{tag}.log"
  to = False
  with open(log, "w") as fh:
    # The tree first on the import path: otherwise a copy of the project installed on the
    # machine shadows the candidate and every tree behaves identically.
    env = {
        **ENV,
        "PYTHONPATH": os.pathsep.join(
            filter(
                None,
                [
                    str(lab / name),
                    str(lab / name / "src"),
                    os.environ.get("PYTHONPATH", ""),
                ],
            )
        ),
    }
    p = subprocess.Popen(
        cmd,
        shell=True,
        cwd=lab / name,
        env=env,
        stdout=fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
      rc = p.wait(timeout)
    except subprocess.TimeoutExpired:
      to, rc = True, -9
      try:
        os.killpg(p.pid, 9)
      except OSError:
        pass
      p.wait()
  tail = log.read_text(errors="replace").strip().splitlines()[-3:]
  return name, {
      "rc": rc,
      "secs": round(time.time() - t0, 1),
      "timeout": to,
      "tail": tail,
  }


def cmd_run(a):
  lab = Path(a.out).resolve()
  names = sorted(p.name for p in lab.iterdir() if p.is_dir())
  if a.only:
    names = [n for n in names if n in a.only.split(",") or n == "_base"]
  cmd = " ".join(a.cmd)
  out = {}
  with cf.ThreadPoolExecutor(a.jobs) as ex:
    for name, res in ex.map(
        lambda n: run_one(lab, n, cmd, a.timeout, a.tag), names
    ):
      out[name] = res
      print(
          f"{name:8} rc={res['rc']:<4} {res['secs']:>6}s"
          f" {'TIMEOUT ' if res['timeout'] else ''}|"
          f" {res['tail'][-1][:150] if res['tail'] else ''}"
      )
  (lab / f"run_{a.tag}.json").write_text(json.dumps(out, indent=1))


def main():
  ap = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  sp = ap.add_subparsers(dest="sub", required=True)
  b = sp.add_parser("build")
  b.add_argument("--base", required=True)
  b.add_argument("--out", required=True)
  b.add_argument("--jobs", type=int, default=4)
  b.add_argument("cands", nargs="+")
  b.set_defaults(fn=cmd_build)
  r = sp.add_parser("run")
  r.add_argument("--out", required=True)
  r.add_argument("--timeout", type=int, default=300)
  r.add_argument("--jobs", type=int, default=4)
  r.add_argument("--only")
  r.add_argument("--tag", default="t")
  r.add_argument("cmd", nargs=argparse.REMAINDER)
  r.set_defaults(fn=cmd_run)
  a = ap.parse_args()
  if a.sub == "run":
    a.cmd = [c for c in a.cmd if c != "--"] if a.cmd[:1] == ["--"] else a.cmd
    if not a.cmd:
      sys.exit("run: give a command after --")
  a.fn(a)


if __name__ == "__main__":
  main()
