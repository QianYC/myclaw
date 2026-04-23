"""MyclawOrchestrator – the core agent loop."""

import enum
import importlib
import importlib.util
from importlib.metadata import entry_points
import json
import os
import pkgutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

import myclaw.tools as tools_pkg
from myclaw.tool_base import get_tools, tool_registry


SYSTEM_PROMPT = """
You are a personal AI assistant. Your job is to handle the tasks user gives you.

# Planning before acting

For non-trivial work, propose a plan before making changes. Call `enter_planning_mode` when:
- The task touches more than one or two files
- Multiple reasonable approaches exist
- Requirements are ambiguous or the change is architectural

Skip planning for: single-line fixes, typo corrections, information-only questions, or tasks the user has already specified in detail.

# While in plan mode

1. Use read-only tools to explore relevant code.
2. Write your plan to the plan file the harness provides.
3. Call `exit_planning_mode` to request approval. Do not ask for plan approval any other way (no text questions, no ask_user_question).
4. If the user revises, update the plan file and call `exit_planning_mode` again.

Do not edit any file except the plan file while in plan mode.

# After approval

Execute the plan step by step. Add new tasks as you discover them, keep the user informed at natural checkpoints, and report results concisely when done.
"""

SYSTEM_PROMPT2 = """
You are a helpful assistant that executes tasks given by the user. You follow the below methodology to complete the tasks:

1. Understand the task: Ask clarifying questions if the task is ambiguous or lacks details.
2. Set the goal: Define the exit criteria based on your understanding of the task requirements.
3. Plan the steps: Break down the task into smaller, manageable steps that lead to the goal.
4. Execute the plan: Once the plan is approved by the user, execute the steps one by one.
5. Retrospect: After each step, think about what had been done, what can be improved. And update the exit criteria/plan if necessary.

You are equipped with a set of useful tools, please proactively use them to complete the tasks.

**Important**: The above methodology is flexible, you have the flexibility to adjust the process based on the complexity of the tasks. For simple tasks, you can skip the planning phase and directly execute. For complex tasks, you might need to iterate on the plan multiple times based on user feedback. Always keep the user informed about your thought process and next steps.
"""


def import_builtin_tools():
    """Discover and import all tool modules under myclaw.tools (recursively)."""
    for _, mod_name, _ in pkgutil.walk_packages(tools_pkg.__path__, prefix="myclaw.tools."):
        importlib.import_module(mod_name)


def import_entrypoint_tools():
    """Discover and load tool plugins registered via the 'myclaw.tools' entry point group."""
    eps = entry_points(group="myclaw.tools")
    for ep in eps:
        try:
            ep.load()  # imports the module, triggering the @tool decorator
        except Exception as e:
            print(f"[Warning] Failed to load entry-point tool '{ep.name}': {e}")


def import_tools_from_directory(tools_dir: str):
    """Load all .py tool files from a user-specified directory (recursively)."""
    tools_path = Path(tools_dir).expanduser().resolve()
    if not tools_path.is_dir():
        print(f"[Warning] Tools directory not found: {tools_path}")
        return
    # Add the parent to sys.path so relative imports inside the folder work
    parent = str(tools_path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    for root, _, files in os.walk(tools_path):
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("__"):
                filepath = os.path.join(root, fname)
                mod_name = (
                    os.path.relpath(filepath, tools_path.parent)
                    .replace(os.sep, ".")
                    .removesuffix(".py")
                )
                try:
                    importlib.import_module(mod_name)
                except Exception as e:
                    print(f"[Warning] Failed to load tool '{mod_name}' from {filepath}: {e}")


def load_all_tools(extra_tools_dir: str | None = None):
    """Load tools from all sources: built-in, entry points, and user directory."""
    import_builtin_tools()
    import_entrypoint_tools()
    if extra_tools_dir:
        import_tools_from_directory(extra_tools_dir)


class Mode(enum.Enum):
    """Agent modes that can be switched between via system prompts or tools."""
    DEFAULT = "default"
    PLANNING = "planning"


@dataclass
class RunTaskResult:
    """Structured result from MyclawOrchestrator.run_task()."""
    output: str
    turns: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    duration_s: float = 0.0
    error: str | None = None

class MyclawOrchestrator:
    """Core agent orchestrator that drives the chat/tool-use loop."""

    def __init__(self, model_name: str, model_endpoint: str, api_key: str,
                 tools_dir: str | None = None):
        self.model_name = model_name
        self.model_endpoint = model_endpoint
        self.api_key = api_key
        self.model = AsyncOpenAI(base_url=model_endpoint, api_key=api_key)
        self.memory = [
            {"role": "system", "content": SYSTEM_PROMPT2},
        ]
        self.mode = Mode.DEFAULT
        # Load tools from all sources
        load_all_tools(extra_tools_dir=tools_dir)

    async def agent_loop(self, user_input: str):
        """Run a single agent turn: append user input and process tool calls until done."""
        self.memory.append({"role": "user", "content": user_input})

        tool_schemas = get_tools()

        while True:
            response = await self.model.chat.completions.create(
                model=self.model_name,
                messages=self.memory,
                tools=tool_schemas,
            )
            choice = response.choices[0]
            self.memory.append(choice.message)

            # No tool calls → final answer
            if not choice.message.tool_calls:
                print(f"\n[Agent Output] {choice.message.content}", end="\n", flush=True)
                break

            # Process tool calls
            tool_results = []
            for tool_call in choice.message.tool_calls:
                tool_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                tool_cls = tool_registry.get(tool_name)
                if tool_cls is not None:
                    tool_instance = tool_cls(orchestrator=self)
                    result = tool_instance.execute(**args)
                else:
                    result = f"[Unknown tool call: {tool_name}]"
                    print(result)
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })
            self.memory.extend(tool_results)

    async def run_task(
        self,
        prompt: str,
        *,
        max_turns: int = 50,
        system_prompt: str | None = None,
        tool_output_max_chars: int = 8000,
    ) -> RunTaskResult:
        """Drive the ReAct loop once with a single prompt and return structured
        metadata. Used by the benchmark harness; does not share memory with
        the REPL and does not print to stdout.

        Tool results are truncated to `tool_output_max_chars` before being
        appended to memory so runaway stdout (e.g., `find /`) doesn't grow the
        context past the endpoint's request-size limit.
        """
        system = system_prompt if system_prompt is not None else SYSTEM_PROMPT2
        memory: list[Any] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        tool_schemas = get_tools()
        tool_calls_log: list[dict[str, Any]] = []
        tokens_in = 0
        tokens_out = 0
        final_output = ""
        error: str | None = None
        t0 = time.time()
        turns = 0

        try:
            for turns in range(1, max_turns + 1):
                response = await self.model.chat.completions.create(
                    model=self.model_name,
                    messages=memory,
                    tools=tool_schemas,
                )
                usage = getattr(response, "usage", None)
                if usage is not None:
                    tokens_in += getattr(usage, "prompt_tokens", 0) or 0
                    tokens_out += getattr(usage, "completion_tokens", 0) or 0

                choice = response.choices[0]
                memory.append(choice.message)

                if not choice.message.tool_calls:
                    final_output = choice.message.content or ""
                    break

                for tool_call in choice.message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as exc:
                        args = {}
                        tool_result = f"[invalid tool arguments: {exc}]"
                    else:
                        tool_cls = tool_registry.get(tool_name)
                        if tool_cls is None:
                            tool_result = f"[Unknown tool call: {tool_name}]"
                        else:
                            instance = tool_cls(orchestrator=self)
                            tool_result = instance.execute(**args)
                    tool_result_str = str(tool_result)
                    memory_content = tool_result_str
                    if len(memory_content) > tool_output_max_chars:
                        head = memory_content[: tool_output_max_chars // 2]
                        tail = memory_content[-tool_output_max_chars // 2 :]
                        memory_content = (
                            f"{head}\n\n... [truncated "
                            f"{len(tool_result_str) - tool_output_max_chars} chars] ...\n\n"
                            f"{tail}"
                        )
                    tool_calls_log.append(
                        {"name": tool_name, "arguments": args, "result": tool_result_str[:4000]}
                    )
                    memory.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": memory_content,
                        }
                    )
            else:
                error = f"max_turns={max_turns} exhausted without final answer"
        except Exception as exc:
            error = f"run_task raised: {type(exc).__name__}: {exc}"

        return RunTaskResult(
            output=final_output,
            turns=turns,
            tool_calls=tool_calls_log,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_s=time.time() - t0,
            error=error,
        )

    async def run_async(self):
        """Interactive REPL loop reading user input and driving `agent_loop`."""
        while True:
            try:
                user_input = input("[User Input] > ")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting. Goodbye!")
                break
            user_input = user_input.strip()
            if user_input.lower() in {"exit", "quit"}:
                print("Exiting. Goodbye!")
                break
            if not user_input:
                continue
            await self.agent_loop(user_input)
