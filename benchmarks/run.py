"""CLI entrypoint for the myclaw benchmark harness.

Runs `myclaw` against Terminal-Bench tasks inside per-task Docker containers
and emits a pass/fail report. Invoke with `python -m benchmarks.run`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .base import RunResult
from .runner import BenchmarkRunner


async def _noop_agent(_prompt: str) -> RunResult:
    """Placeholder AgentRunner. Required by the Benchmark protocol; unused by
    the Docker benchmark, which runs the agent inside the container."""
    raise RuntimeError("agent runner was invoked but no host-side runner is wired")


def _make_benchmark(args: argparse.Namespace):
    if args.benchmark == "terminal-bench-docker":
        # Imported lazily so that importing this module doesn't pull in the
        # docker-specific adapter (and its dependencies) unless requested.
        # pylint: disable=import-outside-toplevel
        from .docker_terminal_bench import DockerTerminalBench
        return DockerTerminalBench(
            tasks_root=Path(args.tasks_dir),
            model=args.model,
            endpoint=args.endpoint,
            api_key=args.api_key,
            max_turns=args.max_turns,
            keep_images=args.keep_images,
        )
    raise SystemExit(f"unknown benchmark: {args.benchmark}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the benchmark harness CLI arguments."""
    p = argparse.ArgumentParser(description="myclaw benchmark harness")
    p.add_argument(
        "--benchmark", required=True,
        choices=["terminal-bench-docker"],
        help="Benchmark to run",
    )
    p.add_argument(
        "--tasks-dir", required=True,
        help="Path to the Terminal-Bench checkout (or its `original-tasks/` "
             "subfolder). Adapter auto-detects the tasks directory.",
    )
    p.add_argument("--model", required=True, help="Model name, e.g. claude-opus-4-7")
    p.add_argument("--endpoint", required=True, help="OpenAI-compatible base URL")
    p.add_argument(
        "--api-key",
        default=os.environ.get("MYCLAW_API_KEY"),
        help="API key (defaults to $MYCLAW_API_KEY)",
    )
    p.add_argument("--output-dir", default="./bench_out",
                   help="Where to write results.jsonl and summary.json")
    p.add_argument("--limit", type=int, default=None,
                   help="Run only the first N supported tasks")
    p.add_argument("--parallelism", type=int, default=4,
                   help="Number of tasks running concurrently")
    p.add_argument("--max-turns", type=int, default=50,
                   help="Per-task cap on agent loop iterations")
    p.add_argument("--keep-images", action="store_true",
                   help="Keep per-task Docker images after the run")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: run the selected benchmark and return a shell exit code."""
    args = parse_args(argv)
    if not args.api_key:
        print("error: --api-key (or $MYCLAW_API_KEY) is required", file=sys.stderr)
        return 2

    benchmark = _make_benchmark(args)
    runner = BenchmarkRunner(output_dir=Path(args.output_dir))

    summary = asyncio.run(
        runner.run(benchmark, _noop_agent, limit=args.limit, parallelism=args.parallelism)
    )
    return 0 if summary["n_passed"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
