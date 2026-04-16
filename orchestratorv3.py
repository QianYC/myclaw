
from openai import AsyncOpenAI
import asyncio
import importlib
import os
import sys
from tool_base import get_tools, tool_registry
import json

SYSTEM_PROMPT = """
You are a person AI assitant. Your job is to handle the tasks user gives you.
"""

# Dynamically import all modules in the tools package to auto-register tools
def import_all_tools():
    import pkgutil
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import tools
    for _, mod_name, _ in pkgutil.walk_packages(tools.__path__, prefix="tools."):
        importlib.import_module(mod_name)

import_all_tools()

class MyclawOrchestrator:
    def __init__(self, model_name: str, model_endpoint: str, api_key: str):
        self.model_name = model_name
        self.model_endpoint = model_endpoint
        self.api_key = api_key
        self.model = AsyncOpenAI(base_url=model_endpoint, api_key=api_key)
        self.memory = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

    async def agent_loop(self, user_input: str):
        self.memory.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        # Get all registered tool schemas
        tool_schemas = get_tools()

        while True:
            response = await self.model.chat.completions.create(
                model=self.model_name,
                messages=self.memory,
                tools=tool_schemas,
            )
            choice = response.choices[0]
            self.memory.append(choice.message)

            # No tool calls → final answer (the plan)
            if not choice.message.tool_calls:
                print(f"\n[Agent Output] {choice.message.content}", end="\n", flush=True)
                break

            # Process tool calls dynamically
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
                    # print(f"[{tool_name} Output]\n{result}")
                else:
                    result = f"[Unknown tool call: {tool_name}]"
                    print(result)
                # Append tool_result message for OpenAI function calling protocol
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })
            # Add all tool_result messages to memory before next round
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

if __name__ == "__main__":
    orchestrator = MyclawOrchestrator(
        model_name="claude-opus-4.7",
        model_endpoint="http://localhost:4141/",
        api_key="your-api-key",
    )
    asyncio.run(orchestrator.run_async())

