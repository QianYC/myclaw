"""Benchmark protocol and shared data types.

Concrete benchmarks implement `Benchmark`. The runner and agent side never
import a concrete benchmark directly — they speak this protocol only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol


@dataclass
class Task:
    """A single benchmark task: an identifier, prompt, and optional workspace."""

    id: str
    prompt: str
    workspace: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Structured result of running one task through the agent."""

    # pylint: disable=too-many-instance-attributes

    output: str
    turns: int
    tool_calls: list[dict[str, Any]]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_s: float
    error: str | None = None


@dataclass
class Grade:
    """Grading output for a task: pass/fail, numeric score, free-form details."""

    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)


AgentRunner = Callable[[str], Awaitable[RunResult]]


class Benchmark(Protocol):
    """Protocol every concrete benchmark adapter must implement."""

    name: str

    def load_tasks(self, limit: int | None = None) -> Iterable[Task]:
        """Yield tasks the runner should execute, optionally capped at `limit`."""

    async def run_task(self, task: Task, agent: AgentRunner) -> RunResult:
        """Execute a single task and return its run result."""

    def grade(self, task: Task, result: RunResult) -> Grade:
        """Grade a completed task's run result."""
