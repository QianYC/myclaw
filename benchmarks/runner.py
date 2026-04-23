"""Benchmark runner: iterates tasks, dispatches to the benchmark adapter,
grades, writes JSONL results and a final summary."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .base import AgentRunner, Benchmark, Grade, RunResult, Task


class BenchmarkRunner:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_path = self.output_dir / "results.jsonl"
        self.summary_path = self.output_dir / "summary.json"

    async def run(
        self,
        benchmark: Benchmark,
        agent: AgentRunner,
        *,
        limit: int | None = None,
        parallelism: int = 4,
    ) -> dict[str, Any]:
        tasks = list(benchmark.load_tasks(limit=limit))
        if not tasks:
            raise RuntimeError(f"{benchmark.name} produced zero tasks")

        print(f"[runner] {benchmark.name}: {len(tasks)} tasks, parallelism={parallelism}")

        # Truncate prior results file so summaries don't blend.
        self.results_path.write_text("")

        sem = asyncio.Semaphore(parallelism)
        start = time.time()
        records: list[dict[str, Any]] = []

        async def execute(task: Task) -> dict[str, Any]:
            async with sem:
                t0 = time.time()
                try:
                    result = await benchmark.run_task(task, agent)
                except Exception as exc:
                    result = RunResult(
                        output="",
                        turns=0,
                        tool_calls=[],
                        tokens_in=0,
                        tokens_out=0,
                        cost_usd=0.0,
                        duration_s=time.time() - t0,
                        error=f"run_task raised: {exc}",
                    )
                try:
                    grade = benchmark.grade(task, result)
                except Exception as exc:
                    grade = Grade(passed=False, score=0.0, details={"grade_error": str(exc)})
                record = {
                    "task_id": task.id,
                    "passed": grade.passed,
                    "score": grade.score,
                    "grade_details": grade.details,
                    "result": asdict(result),
                    "task_metadata": task.metadata,
                }
                self._append_jsonl(record)
                marker = "PASS" if grade.passed else "FAIL"
                print(
                    f"[runner] {marker} {task.id} "
                    f"turns={result.turns} "
                    f"cost=${result.cost_usd:.4f} "
                    f"dur={result.duration_s:.1f}s"
                )
                return record

        for coro in asyncio.as_completed([execute(t) for t in tasks]):
            records.append(await coro)

        summary = self._summarize(benchmark.name, records, time.time() - start)
        self.summary_path.write_text(json.dumps(summary, indent=2))
        print(
            f"[runner] done: pass_rate={summary['pass_rate']:.2%} "
            f"total_cost=${summary['total_cost_usd']:.4f} "
            f"wallclock={summary['wallclock_s']:.1f}s"
        )
        return summary

    def _append_jsonl(self, record: dict[str, Any]) -> None:
        with self.results_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    @staticmethod
    def _summarize(name: str, records: list[dict[str, Any]], wallclock_s: float) -> dict[str, Any]:
        n = len(records)
        passed = sum(1 for r in records if r["passed"])
        durations = [r["result"]["duration_s"] for r in records]
        costs = [r["result"]["cost_usd"] for r in records]
        turns = [r["result"]["turns"] for r in records]
        errors = [r for r in records if r["result"].get("error")]
        return {
            "benchmark": name,
            "n_tasks": n,
            "n_passed": passed,
            "pass_rate": passed / n if n else 0.0,
            "total_cost_usd": sum(costs),
            "total_tokens_in": sum(r["result"]["tokens_in"] for r in records),
            "total_tokens_out": sum(r["result"]["tokens_out"] for r in records),
            "wallclock_s": wallclock_s,
            "mean_duration_s": statistics.mean(durations) if durations else 0.0,
            "median_duration_s": statistics.median(durations) if durations else 0.0,
            "mean_turns": statistics.mean(turns) if turns else 0.0,
            "n_errors": len(errors),
        }
