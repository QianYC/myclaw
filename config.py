"""Typed configuration loaded from settings.yaml."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ModelRouterConfig:
    """Configuration for the model router endpoint."""

    endpoint: str
    api_key: str
    model: str


@dataclass
class ModelConfig:
    """Configuration for an individual LLM model."""

    model: str
    endpoint: str
    api_key: str


@dataclass
class SkillsConfig:
    """Configuration for the skills directory."""

    root: str = "skills"


@dataclass
class McpConfig:
    """Configuration for a single MCP server connection."""

    name: str
    transport: str  # "stdio", "sse", or "http"
    # stdio transport
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # sse / streamable_http transport
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class AppConfig:
    """Top-level application configuration."""

    model_router: Optional[ModelRouterConfig] = None
    models: list[ModelConfig] = field(default_factory=list)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    mcp: list[McpConfig] = field(default_factory=list)
    streaming: bool = True
    workspace: str = "."
    max_loops: int = 5


def load_config(path: str | Path = "settings.yaml") -> AppConfig:
    """Read *settings.yaml* and return a typed AppConfig."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # model_router (optional)
    mr = raw.get("model_router")
    model_router = None
    if mr and mr.get("endpoint") and not mr["endpoint"].startswith("<"):
        model_router = ModelRouterConfig(
            endpoint=mr["endpoint"],
            api_key=mr.get("apiKey", ""),
            model=mr.get("model", ""),
        )

    # models list
    models = [
        ModelConfig(
            model=m["model"],
            endpoint=m["endpoint"],
            api_key=m.get("apiKey", ""),
        )
        for m in raw.get("models", [])
        if m.get("model") and not str(m.get("endpoint", "")).startswith("<")
    ]

    # skills
    skills_raw = raw.get("skills") or {}
    skills = SkillsConfig(root=skills_raw.get("root", "~/.myclaw/skills"))

    # mcp servers
    mcp = []
    for entry in raw.get("mcp", []):
        if not entry or not entry.get("name"):
            continue
        transport = entry.get("transport", "stdio")
        mcp.append(McpConfig(
            name=entry["name"],
            transport=transport,
            command=entry.get("command", ""),
            args=entry.get("args", []),
            env=entry.get("env", {}),
            url=entry.get("url", ""),
            headers=entry.get("headers", {}),
        ))

    # streaming (default True)
    streaming = bool(raw.get("streaming", True))

    # workspace
    workspace = str(raw.get("workspace", "."))
    workspace = str(Path(workspace).expanduser().resolve())

    # maxLoops (default 10)
    max_loops = int(raw.get("maxLoops", 10))

    return AppConfig(
        model_router=model_router,
        models=models,
        skills=skills,
        mcp=mcp,
        streaming=streaming,
        workspace=workspace,
        max_loops=max_loops,
    )
