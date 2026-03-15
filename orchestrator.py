import asyncio
import json
import traceback

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from config import AppConfig, load_config
from memory import Memory, SlidingWindowMemory
from mcp_client import McpManager, McpServer, McpTool, tools_to_openai_format
from skill_client import SkillManager, SkillResult
import os

class MyClawOrchestrator:
    def __init__(self, config: AppConfig):
        print("Initializing MyClawOrchestrator...")
        self.config = config
        if not os.path.exists(config.workspace):
            os.makedirs(config.workspace)
            print(f"Created workspace directory: {config.workspace}")
        else:
            print(f"Using workspace directory: {config.workspace}")
        
        self._loop = asyncio.new_event_loop()  # persistent loop for MCP sessions
        self.skills = SkillManager(config)
        self.mcp = McpManager()
        self.mcp.start()
        self.parse_config(config)
        self.load_skills(config)
        self.load_tools(config)
        self.connect_models(config)
        self.memory : Memory = SlidingWindowMemory(max_size=1000)
        pass

    def parse_config(self, config: AppConfig):
        print("Parsing configuration...")
        # Implement configuration parsing logic here
        self.streaming = config.streaming
        pass

    def load_skills(self, config: AppConfig):
        self.skills.load_skills()
        pass

    def load_tools(self, config: AppConfig):
        self.tools = []
        print("Loading builtin tools...")
        print("Loading custom tools...")
        # Load MCP tools
        if config.mcp:
            print(f"Loading {len(config.mcp)} MCP server(s)...")
            for mcp_cfg in config.mcp:
                try:
                    self.mcp.connect(mcp_cfg)
                except Exception as e:
                    print(f"  [ERROR] MCP server '{mcp_cfg.name}': {e}")
                    traceback.print_exc()
            print(f"  Total MCP tools loaded: {len(self.mcp.tools)}")
            self.tools.extend(tools_to_openai_format(self.mcp.tools))
        else:
            print("No MCP servers configured.")

    def connect_models(self, config: AppConfig):
        print("Connecting to models...")
        # Implement model connection logic here
        if config.model_router:
            print("Using model router...")
            self.model_router = OpenAI(base_url=config.model_router.endpoint, api_key=config.model_router.api_key)
            self.use_model_router = True
        else:
            self.use_model_router = False

        # connect individual models
        self.models = {}
        for m in config.models:
            self.models[m.model] = OpenAI(base_url=m.endpoint, api_key=m.api_key)
        pass

    def shutdown(self) -> None:
        """Clean up MCP servers and the event loop."""
        self.mcp.shutdown()
        self._loop.close()
    
    def chat(self, request: str) -> str:
        print("Find related skills/tools for the request...")
        request = request.strip()
        if request.startswith("/"):
            skill = request.split()[0][1:]
            print(f"Trying to match skill '{skill}'...")
            prompt = self.skills.get_skill(skill)
            if prompt != SkillResult.NOT_FOUND:
                request = request[len(skill)+2:]  # remove the skill command from the request
                print(f"Matched skill '{skill}'.")
                self.memory.add({
                    "role": "system",
                    "content": prompt,
                })
        self.memory.add({
            "role": "user",
            "content": request,
        })

        for i in range(self.config.max_loops):
            print(f"=== Loop {i+1} ===")
            print("Invoke LLM with current memory and tools...")
            if self.use_model_router:
                print("Using model router...")
            else:
                name, model = list(self.models.items())[0]
                print(f"Using individual model {name}...")
                response = model.chat.completions.create(
                    model=name,
                    messages=self.memory.get_messages(),
                    stream=self.streaming,
                    tools=self.tools,
                )

                response_text : str = ""
                tool_calls = {}
                if self.streaming:
                    for chunk in response:
                        delta = chunk.choices[0].delta
                        # parse streaming tool calls
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
                        # parse streaming content
                        if delta.content:
                            response_text += delta.content
                    if response_text:
                        print(f"LLM response: {response_text}")
                    if tool_calls:
                        # Add assistant message with tool_calls to memory FIRST
                        tool_calls_list = [tool_calls[i] for i in sorted(tool_calls)]
                        self.memory.add({
                            "role": "assistant",
                            "content": response_text or None,
                            "tool_calls": [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": tc["arguments"],
                                    },
                                }
                                for tc in tool_calls_list
                            ],
                        })
                        # Then execute each tool and add results
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
                    else:
                        print("No tool calls detected in response.")
                        # Exit loop if no tool calls, assuming response is final answer
                        break
            if i == self.config.max_loops - 1:
                print("Reached maximum loop count. Stopping.")
        pass

if __name__ == "__main__":
    config = load_config()
    orchestrator = MyClawOrchestrator(config=config)
    orchestrator.chat("whats 123*456+1")
    orchestrator.chat("/calc 123*456+1")
    orchestrator.chat("whats 123*456+1")
    orchestrator.shutdown()