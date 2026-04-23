# myclaw benchmark harness

Runs `myclaw` against [Terminal-Bench](https://github.com/laude-institute/terminal-bench)
tasks inside per-task Docker containers and produces a pass/fail report.

```
benchmarks/
├── base.py                      # Benchmark protocol + shared dataclasses
├── runner.py                    # Parallel task dispatch + JSONL / summary output
├── run.py                       # CLI entrypoint (`python -m benchmarks.run`)
├── docker_terminal_bench.py     # Terminal-Bench adapter (the only adapter today)
└── docker/
    ├── Dockerfile.ubuntu-myclaw # base: ubuntu-24-04 + myclaw
    ├── Dockerfile.python-myclaw # base: python-3-13 + myclaw
    ├── entrypoint.sh            # runs inside every task container: agent → grader
    └── agent_runner.py          # in-container driver for MyclawOrchestrator.run_task
```

## Prerequisites

1. **Docker** (Desktop on Windows/Mac, or Docker Engine on Linux) — running.
2. **myclaw installed** in the Python environment you'll use to launch the harness:
   ```bash
   pip install -e .[benchmark]
   ```
3. **Terminal-Bench checkout** anywhere on disk:
   ```bash
   git clone https://github.com/laude-institute/terminal-bench /path/to/terminal-bench
   ```
4. **An OpenAI-compatible model endpoint** reachable from the host. The adapter
   auto-rewrites `localhost`/`127.0.0.1` to `host.docker.internal` so the
   container can reach a local server on the host. The host server must bind
   to `0.0.0.0` (not just `127.0.0.1`) for the container to reach it.

## Run it

From the myclaw repo root:

```bash
python -m benchmarks.run \
    --benchmark terminal-bench-docker \
    --tasks-dir /path/to/terminal-bench \
    --model claude-opus-4-7 \
    --endpoint http://localhost:4141/ \
    --api-key "$MYCLAW_API_KEY" \
    --limit 3 \
    --output-dir ./bench_out
```

(PowerShell: replace the `\` line continuations with backticks.)

First invocation builds the two myclaw-enabled base images (~3–5 minutes).
Subsequent runs skip that step. Per-task derived images build and run in
seconds each after the bases are cached.

## Results

After the run finishes:

| File | Contents |
| --- | --- |
| `bench_out/summary.json` | Aggregate: `pass_rate`, total cost, wallclock, token totals |
| `bench_out/results.jsonl` | One JSON line per task: `passed`, `score`, per-task duration, tool-call log (top 20), container stdout tail |

```bash
cat bench_out/summary.json
head -1 bench_out/results.jsonl | python -m json.tool
```

## Flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--benchmark` | (required) | Only `terminal-bench-docker` today |
| `--tasks-dir` | (required) | Terminal-Bench checkout; adapter finds `original-tasks/` inside |
| `--model` | (required) | Model name passed to the agent |
| `--endpoint` | (required) | OpenAI-compatible base URL |
| `--api-key` | `$MYCLAW_API_KEY` | API key passed into the container |
| `--limit` | all | Run only the first N supported tasks |
| `--parallelism` | 4 | Concurrent tasks (each in its own container) |
| `--max-turns` | 50 | Per-task cap on agent ReAct loop iterations |
| `--keep-images` | off | Preserve per-task Docker images for debugging |
| `--output-dir` | `./bench_out` | Where to write the report files |

## What happens per task

1. Read the task's `task.yaml` and `Dockerfile`. If the `FROM` line doesn't
   match one of the supported bases (ubuntu-24-04 or python-3-13), skip silently.
2. Rewrite the task's `FROM` line to our pre-built `myclaw-enabled` base.
3. Build a per-task image `myclaw-tbench/task-<task-id>` using the task dir as build context.
4. `docker run` the image with:
   - `/myclaw/task-prompt.txt` — the task instruction (mounted)
   - `/myclaw/tests/` — the task's test directory (mounted)
   - `/myclaw/run-tests.sh` — the task's grader (mounted)
   - `MYCLAW_MODEL`, `MYCLAW_ENDPOINT`, `MYCLAW_API_KEY`, `MYCLAW_MAX_TURNS`, `TEST_DIR` env vars
5. Container entrypoint runs `myclaw-oneshot` (drives `MyclawOrchestrator.run_task`), then executes `bash /myclaw/run-tests.sh`.
6. Container exit code is the grade: `0` = pass, anything else = fail.
7. Host harness scrapes a `##MYCLAW_RUN_RESULT##{...}##END##` line from the container's stdout for turns/tokens metadata.

## Coverage

Adapter supports tasks whose `FROM` line contains:

- `ghcr.io/laude-institute/t-bench/ubuntu-24-04` — ~104 tasks
- `ghcr.io/laude-institute/t-bench/python-3-13` — ~99 tasks

That's ~200 of 241 total tasks. The remainder use other bases
(`python:3.11-slim`, `debian:bullseye-slim`, `taichidev/taichi`, etc.) and are
skipped silently by `load_tasks`.

## Adding a new base image

To support a third base (example: `python:3.11-slim`):

1. Create `benchmarks/docker/Dockerfile.python-311-myclaw` modeled on the
   existing ones (change the `FROM` line, keep the rest identical).
2. Append to `BASE_IMAGE_MAP` in `docker_terminal_bench.py`:
   ```python
   "python:3.11-slim": "myclaw-tbench/python-3-11-myclaw",
   ```
3. Append to `BASE_DOCKERFILES`:
   ```python
   "myclaw-tbench/python-3-11-myclaw": "benchmarks/docker/Dockerfile.python-311-myclaw",
   ```

No other files need to change.

## Troubleshooting

**`docker CLI not reachable`**
Docker Desktop isn't running. Start it and retry.

**Container can't reach the model endpoint**
Verify the host server binds `0.0.0.0` (not `127.0.0.1` only). Test with:
```bash
docker run --rm --add-host=host.docker.internal:host-gateway alpine:latest \
    sh -c "apk add -q curl && curl -sS -o /dev/null -w 'HTTP %{http_code}\n' http://host.docker.internal:4141/v1/models"
```

**First run hangs on "building base image"**
Normal — pulls ~500MB–1GB of base layers, installs Python + myclaw. Allow 3–5 minutes. Second run is instant.

**Task fails with `turns=0 tokens_in=0`**
The `##MYCLAW_RUN_RESULT##` marker wasn't found in stdout, meaning `agent_runner.py` crashed early. Inspect `bench_out/results.jsonl`'s `output` field for the actual error.

**Want to debug a single task interactively**
Run with `--keep-images` and `--limit 1`, then:
```bash
docker run --rm -it --entrypoint bash myclaw-tbench/task-<task-id>
```
…to poke around inside the task environment.
