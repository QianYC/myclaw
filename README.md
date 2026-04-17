# myclaw

A lightweight AI agent orchestrator with pluggable tool support.

## Installation

```bash
pip install myclaw
```

Or install from source:

```bash
git clone https://github.com/yuchenqian/myclaw.git
cd myclaw
pip install -e .
```

## Usage

### Command line

```bash
myclaw --model claude-opus-4.7 --endpoint http://localhost:4141/ --api-key your-api-key
```

All three flags (`--model`, `--endpoint`, `--api-key`) are required.

### As a Python module

```bash
python -m myclaw --model claude-opus-4.7 --endpoint http://localhost:4141/ --api-key your-api-key
```

### As a library

```python
import asyncio
from myclaw.orchestrator import MyclawOrchestrator

orchestrator = MyclawOrchestrator(
    model_name="claude-opus-4.7",
    model_endpoint="http://localhost:4141/",
    api_key="your-api-key",
)
asyncio.run(orchestrator.run_async())
```

## Adding custom tools

There are three ways to add tools to myclaw:

### 1. Built-in tools

Create a Python file under `myclaw/tools/` with a class decorated with `@tool`:

```python
from myclaw.tool_base import ToolBase, tool

@tool
class MyTool(ToolBase):
    name = "my-tool"

    def run(self, query: str) -> str:
        """Describe what this tool does."""
        return f"Result for {query}"
```

Built-in tools are auto-discovered and registered at startup.

### 2. Custom tool directory

Point myclaw at a folder of tool `.py` files using `--tools-dir`:

```bash
myclaw --model claude-opus-4.7 --endpoint http://localhost:4141/ --api-key your-key --tools-dir /path/to/my/tools
```

Or via the Python API:

```python
orchestrator = MyclawOrchestrator(
    model_name="claude-opus-4.7",
    model_endpoint="http://localhost:4141/",
    api_key="your-api-key",
    tools_dir="./my-tools",
)
```

### 3. Entry point plugins (third-party packages)

Third-party packages can register tools via the `myclaw.tools` entry point group. In the plugin's `pyproject.toml`:

```toml
[project.entry-points."myclaw.tools"]
my-tool = "my_plugin.tools:MyTool"
```

After `pip install my-plugin`, the tool is automatically available in myclaw — no configuration needed.

All three sources are loaded at startup and merged into a single tool registry.

## Built-in tools

myclaw ships with the following tools out of the box:

| Tool | Description |
|---|---|
| `terminal-tool` | Execute shell commands (PowerShell on Windows, bash on Unix) |
| `web-search` | Search the web using DuckDuckGo |
| `file` | File CRUD operations (read, write, append, delete) |
| `file-search` | Search for content/keywords in files across a directory tree |
| `git-tool` | Execute git commands securely |

### file-search performance

`file-search` automatically uses [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) if it's installed on your system for much faster search. Otherwise it falls back to a Python built-in implementation.

To install ripgrep (optional):

```bash
# Windows (winget)
winget install BurntSushi.ripgrep.MSVC

# macOS
brew install ripgrep

# Ubuntu/Debian
sudo apt install ripgrep
```

## License

Apache 2.0
