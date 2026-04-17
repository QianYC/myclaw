"""MyclawOrchestrator – the core agent loop."""

import importlib
import importlib.util
from importlib.metadata import entry_points
import json
import os
import pkgutil
import sys
from pathlib import Path

from openai import AsyncOpenAI

import myclaw.tools as tools_pkg
from myclaw.tool_base import get_tools, tool_registry


SYSTEM_PROMPT = """
You are a personal AI assistant. Your job is to handle the tasks user gives you.
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


class MyclawOrchestrator:
    """Core agent orchestrator that drives the chat/tool-use loop."""

    def __init__(self, model_name: str, model_endpoint: str, api_key: str,
                 tools_dir: str | None = None):
        self.model_name = model_name
        self.model_endpoint = model_endpoint
        self.api_key = api_key
        self.model = AsyncOpenAI(base_url=model_endpoint, api_key=api_key)
        self.memory = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
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
                    tool_instance = tool_cls()
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
