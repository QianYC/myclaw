"""Main orchestrator for the MyClaw agent loop."""

import json
import os
import traceback

from openai import OpenAI

from config import AppConfig, load_config
from memory import Memory, SlidingWindowMemory
from mcp_client import McpManager, tools_to_openai_format
from skill_client import SkillManager, SkillResult


class MyClawOrchestrator:  # pylint: disable=too-many-instance-attributes
    """Orchestrates the agent loop: skill matching, LLM calls, and tool execution."""

    def __init__(self, app_config: AppConfig):
        print("Initializing MyClawOrchestrator...")
        self.config = app_config
        if not os.path.exists(app_config.workspace):
            os.makedirs(app_config.workspace)
            print(f"Created workspace directory: {app_config.workspace}")
        else:
            print(f"Using workspace directory: {app_config.workspace}")

        self.skills = SkillManager(app_config)
        self.mcp = McpManager()
        self.mcp.start()
        self._parse_config(app_config)
        self._load_skills()
        self._load_tools(app_config)
        self._connect_models(app_config)
        self.memory: Memory = SlidingWindowMemory(max_size=1000)

    def _parse_config(self, app_config: AppConfig):
        """Extract runtime settings from configuration."""
        print("Parsing configuration...")
        self.streaming = app_config.streaming

    def _load_skills(self):
        """Load all skills from the configured directory."""
        self.skills.load_skills()

    def _load_tools(self, app_config: AppConfig):
        """Load built-in and MCP tools."""
        self.tools = []
        print("Loading builtin tools...")
        print("Loading custom tools...")
        if app_config.mcp:
            print(f"Loading {len(app_config.mcp)} MCP server(s)...")
            for mcp_cfg in app_config.mcp:
                try:
                    self.mcp.connect(mcp_cfg)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    print(f"  [ERROR] MCP server '{mcp_cfg.name}': {e}")
                    traceback.print_exc()
            print(f"  Total MCP tools loaded: {len(self.mcp.tools)}")
            self.tools.extend(tools_to_openai_format(self.mcp.tools))
        else:
            print("No MCP servers configured.")

    def _connect_models(self, app_config: AppConfig):
        """Initialise OpenAI client(s) for the configured models."""
        print("Connecting to models...")
        if app_config.model_router:
            print("Using model router...")
            self.model_router = OpenAI(
                base_url=app_config.model_router.endpoint,
                api_key=app_config.model_router.api_key,
            )
            self.use_model_router = True
        else:
            self.use_model_router = False

        self.models = {}
        for m in app_config.models:
            self.models[m.model] = OpenAI(base_url=m.endpoint, api_key=m.api_key)

    def shutdown(self) -> None:
        """Clean up MCP servers."""
        self.mcp.shutdown()

    # ------------------------------------------------------------------
    # Streaming helpers
    # ------------------------------------------------------------------

    def _collect_streaming_chunks(self, response) -> tuple[str, dict]:
        """Consume a streaming response and return (text, tool_calls_dict)."""
        response_text = ""
        tool_calls: dict = {}
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.index not in tool_calls:
                        tool_calls[tc.index] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls[tc.index]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls[tc.index]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls[tc.index]["arguments"] += tc.function.arguments
            if delta.content:
                response_text += delta.content
        return response_text, tool_calls

    def _execute_tool_calls(self, tool_calls_list: list, response_text: str) -> None:
        """Add the assistant message and execute each tool call."""
        self.memory.add({
            "role": "assistant",
            "content": response_text or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_list
            ],
        })
        for tc in tool_calls_list:
            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            print(f"[tool call] {tc['name']}({args})")
            tool_response = self.mcp.call_tool(tc["name"], args)
            print(f"[tool response] {tool_response}")
            self.memory.add({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_response,
            })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _apply_skill(self, request: str) -> str:
        """Inject skill system prompt if request starts with a skill command."""
        if not request.startswith("/"):
            return request
        skill_name = request.split()[0][1:]
        print(f"Trying to match skill '{skill_name}'...")
        prompt = self.skills.get_skill(skill_name)
        if prompt != SkillResult.NOT_FOUND:
            request = request[len(skill_name) + 2:]
            print(f"Matched skill '{skill_name}'.")
            self.memory.add({"role": "system", "content": prompt})
        return request

    def _run_loop_iteration(self) -> bool:
        """Run one agent loop iteration. Returns True if the loop should stop."""
        if self.use_model_router:
            print("Using model router...")
            return False

        name, model = list(self.models.items())[0]
        print(f"Using individual model {name}...")
        response = model.chat.completions.create(
            model=name,
            messages=self.memory.get_messages(),
            stream=self.streaming,
            tools=self.tools,
        )

        if not self.streaming:
            return False

        response_text, tool_calls = self._collect_streaming_chunks(response)
        if response_text:
            print(f"LLM response: {response_text}")

        if not tool_calls:
            print("No tool calls detected in response.")
            return True  # stop loop

        tool_calls_list = [tool_calls[k] for k in sorted(tool_calls)]
        self._execute_tool_calls(tool_calls_list, response_text)
        return False

    def chat(self, request: str) -> str:
        """Process a user message through the agent loop and return the response."""
        print("Find related skills/tools for the request...")
        request = self._apply_skill(request.strip())
        self.memory.add({"role": "user", "content": request})

        for i in range(self.config.max_loops):
            print(f"=== Loop {i+1} ===")
            print("Invoke LLM with current memory and tools...")
            if self._run_loop_iteration():
                break
            if i == self.config.max_loops - 1:
                print("Reached maximum loop count. Stopping.")
        return ""


if __name__ == "__main__":
    config = load_config()
    orchestrator = MyClawOrchestrator(app_config=config)
    orchestrator.chat("whats 123*456+1")
    orchestrator.chat("/calc 123*456+1")
    orchestrator.chat("whats 123*456+1")
    orchestrator.shutdown()
