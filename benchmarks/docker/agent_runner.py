#!/usr/bin/env python3
"""In-container driver: runs `MyclawOrchestrator.run_task` once against a
prompt read from a file, prints structured metadata, then exits.

Mirrors what `run.py` does on the host for non-Docker benchmarks, but lives
inside the container so the agent's tool calls (terminal, file, etc.) operate
on the task environment directly — no docker-exec routing needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from myclaw.orchestrator import MyclawOrchestrator


def main() -> int:
    """Parse args, run the orchestrator once, and emit a JSON summary."""
    p = argparse.ArgumentParser()
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--api-key", required=True)
    p.add_argument("--max-turns", type=int, default=50)
    args = p.parse_args()

    with open(args.prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read().strip()

    orchestrator = MyclawOrchestrator(
        model_name=args.model,
        model_endpoint=args.endpoint,
        api_key=args.api_key,
    )

    result = asyncio.run(
        orchestrator.run_task(prompt, max_turns=args.max_turns)
    )

    # Emit a JSON summary line to stdout. The host harness scrapes this to
    # populate RunResult with tokens/turns/etc. Rest of stdout is free-form
    # agent narration.
    summary = asdict(result)
    # Truncate tool_calls in the summary to keep it parseable at scale.
    summary["tool_calls"] = summary["tool_calls"][:20]
    print("\n##MYCLAW_RUN_RESULT##" + json.dumps(summary) + "##END##")
    if result.error:
        print(f"[myclaw-oneshot] error: {result.error}", file=sys.stderr)
        # Non-zero exit to make the failure visible, but don't mask the grader —
        # the entrypoint continues to the grader regardless.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
