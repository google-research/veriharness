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

"""pageprobe: open a built page the way its reader gets it and report what happens.

  pageprobe.py SERVED_DIR [--page index.html] [--mobile] [--click 12] [--out
  DIR]

Serves ONLY SERVED_DIR on a free local port, loads the page in headless Chromium
and
prints JSON: requests that failed or left the served root, console errors and
uncaught
exceptions, text length, counts of controls / svg children / canvases,
horizontal
overflow, what changed when each visible control was clicked, and a screenshot
path.
Needs the playwright package with an installed Chromium; downloads nothing.
"""

import argparse, functools, hashlib, http.server, json, sys, threading
from pathlib import Path


def serve(root: Path):
  class Quiet(http.server.SimpleHTTPRequestHandler):

    def log_message(self, *args):
      pass

  handler = functools.partial(Quiet, directory=str(root))
  srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
  threading.Thread(target=srv.serve_forever, daemon=True).start()
  return srv


COUNTS = """() => ({
  text: document.body ? document.body.innerText.length : 0,
  buttons: document.querySelectorAll('button,[role=button],input[type=button],input[type=submit]').length,
  inputs: document.querySelectorAll('input,select,textarea').length,
  svg_children: [...document.querySelectorAll('svg')].reduce((n, s) => n + s.querySelectorAll('*').length, 0),
  canvases: document.querySelectorAll('canvas').length,
  images_broken: [...document.images].filter(i => i.complete && i.naturalWidth === 0).length,
  overflow_x: document.documentElement.scrollWidth - document.documentElement.clientWidth})"""


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("root")
  ap.add_argument("--page", default="index.html")
  ap.add_argument("--mobile", action="store_true", help="390x844 viewport")
  ap.add_argument(
      "--click",
      type=int,
      default=12,
      help="click at most this many visible controls",
  )
  ap.add_argument(
      "--out",
      default=None,
      help="directory for the screenshot (default: alongside nothing, /tmp)",
  )
  a = ap.parse_args()
  root = Path(a.root).resolve()
  if not (root / a.page).is_file():
    print(json.dumps({"error": f"{a.page} not found under {root}"}))
    return 1
  try:
    from playwright.sync_api import sync_playwright
  except ImportError:
    print(
        json.dumps(
            {"error": "playwright is not installed; fall back to static checks"}
        )
    )
    return 2
  srv = serve(root)
  origin = f"http://127.0.0.1:{srv.server_address[1]}"
  rep = {
      "failed_requests": [],
      "outside_root": [],
      "console_errors": [],
      "page_errors": [],
      "clicks": [],
  }
  try:
    with sync_playwright() as pw:
      try:
        browser = pw.chromium.launch(
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
            ]
        )
      except Exception as e:  # noqa: BLE001
        print(
            json.dumps({
                "error": (
                    f"browser will not launch ({str(e)[:160]}); fall back to"
                    " static checks"
                )
            })
        )
        return 2
      page = browser.new_page(
          viewport={"width": 390, "height": 844}
          if a.mobile
          else {"width": 1280, "height": 900}
      )
      page.on(
          "console",
          lambda m: m.type == "error"
          and rep["console_errors"].append(m.text[:300]),
      )
      page.on("pageerror", lambda e: rep["page_errors"].append(str(e)[:300]))
      page.on(
          "response",
          lambda r: r.status >= 400
          and rep["failed_requests"].append(f"{r.status} {r.url}"),
      )
      page.on(
          "requestfailed",
          lambda r: rep["failed_requests"].append(f"failed {r.url}"),
      )
      page.on(
          "request",
          lambda r: (not r.url.startswith((origin, "data:", "blob:", "about:")))
          and rep["outside_root"].append(r.url[:200]),
      )
      page.route(
          "**/*",
          lambda route: route.abort()
          if not route.request.url.startswith(
              (origin, "data:", "blob:", "about:")
          )
          else route.continue_(),
      )
      page.goto(f"{origin}/{a.page}", wait_until="load", timeout=30000)
      page.wait_for_timeout(1500)
      rep["dom"] = page.evaluate(COUNTS)
      digest = lambda: hashlib.md5(page.content().encode()).hexdigest()  # noqa: E731
      controls = page.locator(
          "button:visible, [role=button]:visible, select:visible,"
          " input[type=checkbox]:visible"
      )
      for i in range(min(a.click, controls.count())):
        el = controls.nth(i)
        try:
          label = (
              el.inner_text(timeout=500) or el.get_attribute("aria-label") or ""
          )[:40]
          before = digest()
          el.click(timeout=1500)
          page.wait_for_timeout(300)
          rep["clicks"].append(
              {"control": label, "dom_changed": digest() != before}
          )
        except Exception as e:  # noqa: BLE001
          rep["clicks"].append({"control": f"#{i}", "error": str(e)[:120]})
      shot = (
          Path(a.out or "/tmp")
          / f"pageprobe_{root.parent.name}_{'m' if a.mobile else 'd'}.png"
      )
      shot.parent.mkdir(parents=True, exist_ok=True)
      try:
        page.screenshot(path=str(shot), full_page=True, timeout=5000)
        rep["screenshot"] = str(shot)
      except Exception as e:
        rep["screenshot"] = ""
        rep["screenshot_error"] = str(e)[:200]
      browser.close()
  finally:
    srv.shutdown()
  for k in ("failed_requests", "outside_root", "console_errors", "page_errors"):
    rep[k] = sorted(set(rep[k]))[:20]
  print(json.dumps(rep, indent=1))
  return 0


if __name__ == "__main__":
  sys.exit(main())
