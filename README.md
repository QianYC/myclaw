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

Or with defaults:

```bash
myclaw
```

### As a Python module

```bash
python -m myclaw --model claude-opus-4.7
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

Tools are auto-discovered and registered at startup.

## License

Apache 2.0
