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

import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


class MaterializeResumeTest(unittest.TestCase):

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    with mock.patch.dict(
        os.environ, {"VERIHARNESS_BENCH_ROOT": str(self.root)}
    ):
      self.base = importlib.import_module("harness.materialize.base")
    patcher = mock.patch.object(self.base, "DATA", self.root / "data")
    patcher.start()
    self.addCleanup(patcher.stop)
    self.pool = self.root / "data" / "fixture" / "small"

  def task(self, key):
    return self.base.Task(
        key=key,
        spec="Fixture task " + key,
        rollouts={
            "seed-b": self.base.Rollout(
                seed="seed-b", score=0.8, texts=[("answer.txt", "B")]
            ),
            "seed-a": self.base.Rollout(
                seed="seed-a", score=0.2, texts=[("answer.txt", "A")]
            ),
        },
    )

  def run_pool(self, tasks, extra=()):
    return self.base.run_cli(
        "fixture", ["small"], tasks, ["--pool", "small", *extra]
    )

  def metadata(self):
    return json.loads((self.pool / "meta.json").read_text())

  def test_completed_metadata_survives_later_iterator_failure(self):
    def interrupted(_):
      yield self.task("first")
      raise RuntimeError("archive unavailable")

    with self.assertRaisesRegex(RuntimeError, "archive unavailable"):
      self.run_pool(interrupted)
    self.assertTrue((self.pool / ".done" / "first").exists())
    self.assertEqual(set(self.metadata()), {"first"})
    self.run_pool(lambda _: iter([self.task("first"), self.task("second")]))
    self.assertEqual(set(self.metadata()), {"first", "second"})
    self.assertEqual(self.metadata()["first"]["rollouts"]["r01"]["score"], 0.2)

  def test_orphaned_marker_without_metadata_is_rebuilt(self):
    marker = self.pool / ".done" / "first"
    marker.parent.mkdir(parents=True)
    marker.touch()
    self.run_pool(lambda _: iter([self.task("first")]))
    self.assertEqual(set(self.metadata()), {"first"})
    self.assertEqual(
        (
            self.pool / "tasks/first/rollouts/r01/deliverables/answer.txt"
        ).read_text(),
        "A",
    )

  def test_successful_resume_skips_existing_workspace(self):
    tasks = lambda _: iter([self.task("first")])
    self.run_pool(tasks)
    path = self.pool / "tasks/first/rollouts/r01/deliverables/answer.txt"
    path.write_text("preserve on resume")
    self.run_pool(tasks)
    self.assertEqual(path.read_text(), "preserve on resume")
    self.assertEqual(set(self.metadata()), {"first"})

  def test_materialization_failure_does_not_mark_failed_task(self):
    broken = self.task("second")
    broken.workspace = [(self.root / "missing.txt", "input.txt")]
    with self.assertRaises(FileNotFoundError):
      self.run_pool(lambda _: iter([self.task("first"), broken]))
    self.assertFalse((self.pool / ".done" / "second").exists())
    self.assertEqual(set(self.metadata()), {"first"})

  def test_failed_metadata_replace_preserves_previous_snapshot(self):
    self.run_pool(lambda _: iter([self.task("first")]))
    before = (self.pool / "meta.json").read_bytes()
    with mock.patch.object(
        Path, "replace", side_effect=OSError("write failed")
    ):
      with self.assertRaisesRegex(OSError, "write failed"):
        self.run_pool(lambda _: iter([self.task("second")]))
    self.assertEqual((self.pool / "meta.json").read_bytes(), before)
    self.assertFalse((self.pool / ".done" / "second").exists())
    self.run_pool(lambda _: iter([self.task("second")]))
    self.assertEqual(set(self.metadata()), {"first", "second"})

  def test_empty_and_limited_pools_keep_metadata_contract(self):
    self.run_pool(lambda _: iter([]))
    self.assertEqual(self.metadata(), {})
    self.run_pool(
        lambda _: iter([self.task("first"), self.task("second")]),
        ("--limit", "1"),
    )
    self.assertEqual(set(self.metadata()), {"first"})
    self.assertFalse((self.pool / ".done" / "second").exists())


if __name__ == "__main__":
  unittest.main()
