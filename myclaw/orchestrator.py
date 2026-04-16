"""MyclawOrchestrator – the core agent loop."""

from openai import AsyncOpenAI
import asyncio
import importlib
import json
import pkgutil

from myclaw.tool_base import get_tools, tool_registry


SYSTEM_PROMPT = """
You are a personal AI assistant. Your job is to handle the tasks user gives you.
"""


def import_all_tools():
    """Discover and import all tool modules under myclaw.tools (recursively)."""
    import myclaw.tools as tools_pkg
    for _, mod_name, _ in pkgutil.walk_packages(tools_pkg.__path__, prefix="myclaw.tools."):
        importlib.import_module(mod_name)


class MyclawOrchestrator:
    def __init__(self, model_name: str, model_endpoint: str, api_key: str):
        self.model_name = model_name
        self.model_endpoint = model_endpoint
        self.api_key = api_key
        self.model = AsyncOpenAI(base_url=model_endpoint, api_key=api_key)
        self.memory = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        # Auto-load built-in tools
        import_all_tools()

    async def agent_loop(self, user_input: str):
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
                    try:
                        result = tool_instance.run(**args)
                    except Exception as e:
                        result = f"[Tool Error] {e}"
                        print(result)
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
