# VeriHarness

VeriHarness is a verification harness for long-horizon workspace agents. Given
a task and *N* independent rollouts of the same agent on it, VeriHarness uses
**the same model that generated the rollouts** to check them against the task
environment and to deliver one artifact that is better than a typical rollout,
together with a record of the evidence behind every change.

The verifier is not a stronger judge. Its advantage comes from two sources
only: the structure of the rollout pool, and evidence it actively acquires
from the environment (files, data, recomputable quantities).

This is not an officially supported Google product.

## How it works

Rollouts of one model either disagree on a claim or agree on it, and the two
cases call for different checks:

*   **Disagreement → resolve.** The alternatives are already on the table. The
    *resolver* picks the check that best separates them, runs it against the
    environment, and eliminates the candidates the evidence contradicts.
*   **Consensus → challenge.** Agreement is not evidence: rollouts share a
    model and therefore blind spots. The *challenger* looks for ways a shared
    value, a shared reading, or a shared omission could be wrong, and tests
    them.

Each task runs four model turns in three mutually isolated sessions:

```
materialized task ──► resolver    (own session) ──► ledger_elim.json
                 └──► challenger  (own session) ──► ledger_fals.json
                              │   (run concurrently; neither sees the other)
                              ▼
                  adjudication (fresh session: both records + task + rollouts)
                              │        └─► finish.json  {base, work[], open[]}
                              ▼
                  delivery (same session) ──► out/deliverables/ + repair.json
```

Adjudication names a **base** rollout, an evidence-backed **revision plan**
(`work`), and the claims the evidence left **unresolved** (`open`). Selection,
revision and reconstruction are one knob: an empty plan returns the base
unchanged, a non-empty plan revises it, and `base: "none"` rebuilds the artifact
from the task inputs.

The program only materializes workspaces, routes files between sessions and
collects outputs. Which claims to examine, which checks to run and when to stop
are the model's decisions. The single programmatic gate is content-blind: a
delivered bundle must contain every file of its base under the same name.

## Repository layout

```
harness/
  driver.py        one task: the four turns above
  runner.py        many tasks: global work pool with per-model and per-benchmark caps; resumable
  score.py         score a run against the archived pool (selection and final scores)
  config.py        locations and model lanes; all host specifics come from the environment
  views.py         plain-text views rendered beside binary artifacts (.cells.tsv, .text.txt)
  prompts/         CHARTER (system prompt), MISSION, the two investigation playbooks and
                   record formats, ADJUDICATE, REPAIR
  skills/          the skill library (evidence-*, resolve-*, falsify-*, repair-*)
  materialize/     adapters that turn a benchmark's archived rollouts into task workspaces
  grade/           wrappers around each benchmark's own grader, for re-grading revised artifacts
  env/             optional native execution environments (task images) and the office/docs images
  scripts/         mount-namespace jail, agent-runtime setup, benchmark setup, local model proxy
  benchmarks/      our grading configuration and credential templates per benchmark
  pi-home/         the agent runtime's model registry (models.json)
```

## Setup

Requirements: Linux with unprivileged user namespaces (for the jail), Python
3.10+, Node.js 20+ (for the agent runtime), and Docker for the graders and the
optional native environments.

```bash
pip install -r requirements.txt
harness/scripts/setup_pi.sh          # installs the pinned pi agent runtime into harness/vendor/
```

The harness drives the open-source [pi](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)
coding-agent runtime and works with any model provider pi supports (Anthropic,
OpenAI, Google AI Studio, Vertex AI, OpenAI-compatible endpoints and others);
no Google account or service is required. A *lane*
is the verifier model; by default a pool is verified by the model that
generated it. The two lanes used in the paper are defined in
`harness/config.py` (`LANES`); edit them or pass `--provider`/`--model` to the
driver to use other models, for example
`--provider anthropic --model claude-opus-4-8` with `ANTHROPIC_API_KEY` set.

*   **Gemini on Vertex AI** (`flash` lane): pi's `google-vertex` provider with
    application-default credentials (`gcloud auth application-default login`)
    and `GOOGLE_CLOUD_PROJECT` set. The jail exposes `~/.config/gcloud`
    read-only for this purpose.
*   **Claude on Vertex AI** (`opus` lane): served through a local
    [litellm](https://github.com/BerriAI/litellm) proxy that the runner starts
    on demand (`harness/scripts/litellm_up.sh`, port 4180; the registry entry
    is `vertex-litellm` in `harness/pi-home/models.json`):

    ```bash
    harness/scripts/setup_litellm.sh
    export VERTEX_PROJECT=<your-gcp-project>       # and optionally VERTEX_LOCATION
    ```

Host-specific locations are environment variables (see `harness/config.py`):

| Variable | Meaning | Default |
|---|---|---|
| `VERIHARNESS_DATA` | materialized rollout pools | `./data` |
| `VERIHARNESS_RUNS` | run outputs | `./runs` |
| `VERIHARNESS_BENCH_ROOT` | upstream benchmark checkouts and archived rollouts (materialize and grade only) | unset |

## Usage

**Task workspace.** Everything the verifier sees is a directory:

```
<data>/<bench>/<pool>/tasks/<task-key>/
  spec/task.md                        the task description
  workspace/                          the task's input files
  rollouts/rNN/deliverables/          what rollout NN delivered
  rollouts/rNN/trajectory/            its execution trace, if available
<data>/<bench>/<pool>/meta.json       archived per-rollout scores; never visible to the verifier
```

`python3 -m harness.materialize <bench>` builds these from an archive of
rollouts. The adapters encode the archive layout our pools were generated
into; to verify your own rollouts, produce the layout above directly or write
an adapter that yields `materialize.base.Task` objects.

**Run one task.**

```bash
python3 -m harness.driver <task-dir> --provider google-vertex --model gemini-3.5-flash --thinking high
```

The driver writes the two records, `finish.json`, `driver.log` and
`out/deliverables/` into the task directory. `--contract pick-only` stops
after adjudication (selection only), `--no-skills` runs with an empty skill
library, `--skill <dir>` swaps in another library, and `--no-jail` runs
without the jail (debugging only).

**Run a benchmark.** A cell is one `bench:pool` pair; the runner copies each
task workspace under `<runs>/<run-name>/<bench>_<pool>/` and drives the tasks
through the driver with per-lane and per-benchmark concurrency caps. It is
resumable: finished tasks are skipped, unfinished ones re-staged.

```bash
python3 -m harness.runner --run-name demo --cells sb2:opus apex:opus
python3 -m harness.score runs/demo/sb2_opus --workers 24
```

`score.py` reports the single-rollout mean, the selection score, the final
score after revision, and the selection oracle. `--select-only` uses only the
archived scores and needs no grader; otherwise the delivered bundle and the
unrevised base are re-graded in the same pass and
`final = select + (revised − base_regraded)`, so grader drift and judge noise
cancel in the difference.

## Benchmarks and grading

The paper evaluates on APEX-Agents, Workspace-Bench Lite, WorkBuddy Bench,
SpreadsheetBench 2 and JobBench. This repository does not redistribute any
benchmark data, rollouts or images. `harness/scripts/setup_benchmarks.sh`
installs what re-grading needs under `$VERIHARNESS_BENCH_ROOT/benchmarks/`:
each benchmark's own code cloned at the commit the paper's graders were
validated against, its data from Hugging Face, and its environment and
Docker images built with its own tooling.

```bash
export VERIHARNESS_BENCH_ROOT=/path/to/benchmarks-root
harness/scripts/setup_benchmarks.sh sb2 jb          # or: all; --no-images skips the Docker builds
```

| Bench | Upstream (pinned) | Grader and what it needs at scoring time |
|---|---|---|
| `apex` | [archipelago](https://github.com/Mercor-Intelligence/archipelago) grading runner at its current head (the repository rewrites its history, so the paper's exact judge version cannot be pinned; the interface we call was checked on 2026-09-22) | the benchmark's rubric judge with our settings in `harness/benchmarks/apex/`; `GEMINI_API_KEY` (several keys may be comma-separated and are rotated) or `APEX_JUDGE_MODEL=vertex_ai/<model>` with `VERTEXAI_PROJECT` and `VERTEXAI_LOCATION` |
| `wsb` | [Workspace-Bench](https://github.com/OpenDataBox/Workspace-Bench) `a3a2ee4` | the benchmark's agent-as-a-judge in its Docker image; judge endpoint in the checkout's `evaluation/.env` (template: `harness/benchmarks/wsb/env.example`) |
| `wb` | [workbuddy-bench](https://github.com/Tencent/workbuddy-bench) `b516950` | the benchmark's composite verifier in each task's own image (built per task by the setup script); judge endpoint in the checkout's `.env` (template: `harness/benchmarks/wb/env.example`) |
| `sb2` | [SpreadsheetBench-2](https://github.com/RUCKBReasoning/SpreadsheetBench-2) `5c16026` | the official recalculation and cell comparison; LibreOffice in the official image plus `tqdm` (`veriharness-sb2`). The Visualization category is not wrapped |
| `jb` | [job-bench-eval](https://github.com/Job-Bench/job-bench-eval) `0152c80`. The paper's archived scores were produced with one local change to its judge: rubrics on which the judge call failed were re-judged and, if still failing, excluded from both numerator and denominator instead of scored 0 | the benchmark's text judge through an OpenAI-compatible endpoint: `JB_JUDGE_MODEL`, `JB_JUDGE_API_BASE`, `JB_JUDGE_API_KEY` |

`harness/grade/<bench>.py` documents, per benchmark, which upstream entry
point is wrapped. Scoring refuses to start when a judge is unreachable
(`preflight`), because a dead LLM judge scores every rubric 0.0 instead of
raising, and it warns when re-grading the archived bases does not reproduce
their archived scores.

The `harness/materialize/` adapters build task workspaces from the archived
rollout pools of the paper; they document how those pools were produced and
are not needed to verify your own rollouts (see "Task workspace" above).

## Isolation

Verifier sessions run inside `harness/scripts/jail_run.sh`, a mount-namespace
jail (`unshare -r -m -p`, no privileges needed): the task workspace is the
only visible project state, `spec/`, `workspace/` and `rollouts/` are
read-only, the rest of `$HOME`, the data root, `/tmp` and `/var/tmp` are
hidden, the Python installation is read-only, and container runtimes are
masked. Archived scores and benchmark answer keys are therefore unreachable
from a session. There is no network namespace, so model endpoints stay
reachable. Graders run on the host after the verifier batch, never inside
the jail.

## Native environments (optional)

By default every turn runs in the host jail. With `--env native` the
adjudication and delivery turns run inside a fresh container of the
benchmark's own task image, so the verifier revises the artifact with the
interpreter, libraries and tools the rollouts were produced with; the two
investigations stay in the jail. `--env native-full` runs the investigations
in the image as well. A task without an image falls back to the jail for
every turn. The container sees the task directory at its real path (evidence
read-only), the agent runtime and skills read-only, and the host network,
which is the same exposure the jail has.

```bash
python3 -m harness.runner --run-name demo --cells jb:opus --driver-arg=--env --driver-arg=native
```

Images are resolved per benchmark (`harness/env/__init__.py`); each can be
overridden with `VERIHARNESS_IMAGE_<BENCH>`:

| Bench | Default image |
|---|---|
| `wb` | each task's own exported environment image, or its `vh/<name>` derivative when built with `python3 -m harness.env.derive` (the task image plus the harness tool stack) |
| `sb2`, `jb` | `veriharness-office`: `docker build -f harness/env/Dockerfile.office -t veriharness-office .` (on top of the SpreadsheetBench image) |
| `wsb` | `workspace-bench:local` (the benchmark's image) |
| `apex` | `veriharness-docs`: `docker build -f harness/env/Dockerfile.apex -t veriharness-docs .` |

Two things a native setup must provide. Task images carry no JavaScript
runtime, so the agent runs on a self-contained Node.js 22 placed under
`harness/vendor/node-v22/` (the official Linux tarball, extracted there). And
a task image must carry the libraries the skills use, or the verifier's
revisions degrade: keep the tool stack in the image, not only the task's own
dependencies (`harness/env/derive.py` adds it to WorkBuddy's task images).

## Skills

A skill is a short text (optionally with scripts) describing a reusable
failure mode and how to check for it. Skills are mounted by file-name match
against the delivered artifacts (`applies-to:` in the frontmatter) and by
phase (`phase:`); they never contain task-specific answers. They are
organised by phase: `evidence-*` (tools for reading and comparing artifacts;
every phase), `resolve-*` (what evidence settles a disagreement; resolver),
`falsify-*` (how a consensus can be wrong; challenger) and `repair-*` (how to
revise an artifact without breaking it; delivery). Adjudication receives only
the `evidence-*` skills.

Provenance: the `evidence-*`, `falsify-*` and `repair-*` texts are the
human-authored library of the paper. `resolve-*`, `evidence-patch`,
`evidence-bundle`, `repair-patch` and the `xlsx_gaps` / `xlsx_forks` scanners
were written afterwards from failure analyses of the harness on the paper's
benchmarks, including lessons from the self-evolution experiments on
SpreadsheetBench 2 (only reference-free, benchmark-agnostic procedures were
kept; scripts that filled cells automatically or encoded a benchmark's
reference conventions were not).

## Citation

```bibtex
@article{veriharness2026,
  title  = {VeriHarness: Scaling Agentic Verification for Long-Horizon Tasks},
  author = {Zhang, Caiqi and Han, Rujun and Wang, Zifeng and CuiZhu, Zoey and Collier, Nigel and Pfister, Tomas and Lee, Chen-Yu},
  year   = {2026}
}
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). This project follows
[Google's Open Source Community Guidelines](https://opensource.google/conduct/);
see [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

Apache 2.0; see [`LICENSE`](LICENSE).

## Acknowledgements

The verifier runs on the [pi](https://github.com/earendil-works/pi) coding-agent
runtime. Re-grading uses the benchmarks' own graders: the
[APEX-Agents](https://github.com/Mercor-Intelligence/archipelago) grading runner,
[Workspace-Bench](https://github.com/OpenDataBox/Workspace-Bench),
[WorkBuddy Bench](https://github.com/Tencent/workbuddy-bench),
[SpreadsheetBench 2](https://github.com/RUCKBReasoning/SpreadsheetBench-2) and
[JobBench](https://github.com/Job-Bench/job-bench-eval).

## Disclaimer

This is not an officially supported Google product. This project is not
eligible for the [Google Open Source Software Vulnerability Rewards
Program](https://bughunters.google.com/open-source-security).
