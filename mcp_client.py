"""MCP (Model Context Protocol) client helpers."""

import asyncio
import json
import threading
import traceback
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from config import McpConfig

# MCP SDK imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client


@dataclass
class McpTool:
    """A tool exposed by an MCP server, ready for OpenAI function-calling."""
    server_name: str
    name: str
    description: str
    input_schema: dict


@dataclass
class McpServer:
    """A connected MCP server with its session and tools."""
    name: str
    config: McpConfig
    session: ClientSession | None = None
    tools: list[McpTool] = field(default_factory=list)


async def _list_tools(cfg: McpConfig, session: ClientSession) -> list[McpTool]:
    """List tools from an initialized session."""
    result = await session.list_tools()
    return [
        McpTool(
            server_name=cfg.name,
            name=t.name,
            description=t.description or "",
            input_schema=t.inputSchema,
        )
        for t in result.tools
    ]


class McpManager:
    """Manages MCP server connections in a background thread with a single event loop.

    A single long-lived coroutine (_worker) processes all operations via an async
    queue, so anyio cancel scopes are always entered and exited in the same Task.
    """

    def __init__(self) -> None:
        self._servers: list[McpServer] = []
        self._tools: list[McpTool] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        # Will be created inside the loop
        self._queue: asyncio.Queue | None = None
        # Mapping of tool name (<MCP server name>__<tool name>) to session for quick lookup during tool calls
        self._tool_table: dict[str, ClientSession] = {}

    @property
    def servers(self) -> list[McpServer]:
        return self._servers

    @property
    def tools(self) -> list[McpTool]:
        return self._tools

    def start(self) -> None:
        """Start the background event loop thread."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        """Entry point for the background thread — runs the single worker task."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue()
        self._ready.set()
        self._loop.run_until_complete(self._worker())
        self._loop.close()

    async def _worker(self) -> None:
        """Single long-lived coroutine that owns the AsyncExitStack.

        All connect/call_tool/cleanup happen here, in one Task.
        """
        async with AsyncExitStack() as stack:
            self._stack = stack
            while True:
                op, args, result_future = await self._queue.get()
                if op == "shutdown":
                    result_future.set_result(None)
                    break  # exiting 'async with' will aclose the stack
                try:
                    result = await self._dispatch(op, args)
                    result_future.set_result(result)
                except Exception as e:
                    result_future.set_exception(e)
        # Stack is now closed — clean up server references
        for server in self._servers:
            server.session = None
        print("  MCP connections closed.")

    async def _dispatch(self, op: str, args: dict):
        """Route an operation to the right handler."""
        if op == "connect":
            return await self._connect(args["cfg"])
        elif op == "call_tool":
            return await self._call_tool(args["tool_name"], args["arguments"])
        else:
            raise ValueError(f"Unknown MCP operation: {op}")

    def _submit(self, op: str, args: dict):
        """Submit an operation to the worker and block until done."""
        future = asyncio.Future(loop=self._loop)
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (op, args, future))
        # Block the calling thread until the worker completes the operation
        concurrent_future = asyncio.run_coroutine_threadsafe(
            self._await_future(future), self._loop
        )
        return concurrent_future.result()

    @staticmethod
    async def _await_future(future: asyncio.Future):
        return await future

    def connect(self, cfg: McpConfig) -> McpServer:
        """Connect to an MCP server (called from the main thread)."""
        return self._submit("connect", {"cfg": cfg})

    async def _connect(self, cfg: McpConfig) -> McpServer:
        """Async implementation — runs inside the worker task."""
        print(f"  Connecting to MCP server '{cfg.name}' ({cfg.transport})...")
        if cfg.transport == "stdio":
            print(f"    command: {cfg.command} {' '.join(cfg.args)}")
        elif cfg.transport in ("sse", "http"):
            print(f"    url: {cfg.url}")

        try:
            if cfg.transport == "stdio":
                params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args,
                    env=cfg.env or None,
                )
                read_stream, write_stream = await self._stack.enter_async_context(
                    stdio_client(params)
                )
            elif cfg.transport == "sse":
                read_stream, write_stream = await self._stack.enter_async_context(
                    sse_client(url=cfg.url, headers=cfg.headers or None)
                )
            elif cfg.transport == "http":
                read_stream, write_stream = await self._stack.enter_async_context(
                    streamable_http_client(url=cfg.url, headers=cfg.headers or None)
                )
            else:
                raise ValueError(f"Unknown MCP transport: {cfg.transport}")

            session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
        except Exception as e:
            raise ConnectionError(
                f"Failed to initialize MCP server '{cfg.name}' ({cfg.transport}): {e}"
            ) from e

        tools = await _list_tools(cfg, session)
        print(f"\t'{cfg.name}' connected — {len(tools)} tool(s) available")
        for t in tools:
            print(f"\t\t- {t.name}: {t.description[:80]}")

        server = McpServer(name=cfg.name, config=cfg, session=session, tools=tools)
        self._servers.append(server)
        self._tools.extend(tools)
        # Populate the mappings
        for tool in tools:
            self._tool_table[f"{server.name}__{tool.name}"] = session
        return server

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool (from the main thread)."""
        return self._submit("call_tool", {
            "tool_name": tool_name, "arguments": arguments
        })

    async def _call_tool(self, tool_name: str, arguments: dict) -> str:
        session = self._tool_table.get(tool_name)
        if session is None:
            return f"[error] Tool '{tool_name}' not found. Available tools: {list(self._tool_table.keys())}"
        # Strip the server name prefix — MCP expects just the tool name
        raw_tool_name = tool_name.split("__", 1)[-1] if "__" in tool_name else tool_name
        try:
            result = await session.call_tool(raw_tool_name, arguments)
            return "\n".join(
                part.text for part in result.content if hasattr(part, "text")
            )
        except Exception as e:
            return f"[error] Tool '{tool_name}' failed: {type(e).__name__}: {e}"

    def shutdown(self) -> None:
        """Signal the worker to clean up and stop."""
        if self._loop and self._queue:
            future = asyncio.Future(loop=self._loop)
            self._loop.call_soon_threadsafe(
                self._queue.put_nowait, ("shutdown", {}, future)
            )
        if self._thread:
            self._thread.join(timeout=10)


def tools_to_openai_format(mcp_tools: list[McpTool]) -> list[dict]:
    """Convert MCP tools to OpenAI function-calling tool schema."""
    return [
        {
            "type": "function",
            "function": {
                "name": f"{tool.server_name}__{tool.name}",
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in mcp_tools
    ]
