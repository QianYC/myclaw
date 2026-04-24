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
    id: str
    prompt: str
    workspace: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
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
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)


AgentRunner = Callable[[str], Awaitable[RunResult]]


class Benchmark(Protocol):
    name: str

    def load_tasks(self, limit: int | None = None) -> Iterable[Task]: ...

    async def run_task(self, task: Task, agent: AgentRunner) -> RunResult: ...

    def grade(self, task: Task, result: RunResult) -> Grade: ...
