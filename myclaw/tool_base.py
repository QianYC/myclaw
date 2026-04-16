"""
Base class and class-level decorator for defining tools in a structured way.
"""

from typing import Any, Dict, Type

# Registry to keep track of all tool classes
tool_registry: Dict[str, Type['ToolBase']] = {}

import inspect
import json

def tool(cls: Type['ToolBase']) -> Type['ToolBase']:
    """
    Class-level decorator to register a tool class and auto-generate a tool schema.
    """
    name = getattr(cls, 'name', cls.__name__)
    tool_registry[name] = cls

    # Auto-generate tool schema from run() signature and docstring
    sig = inspect.signature(cls.run)
    params = list(sig.parameters.values())[1:]  # skip 'self'
    properties = {}
    required = []
    from typing import get_origin, get_args, Dict as TypingDict

    def type_to_schema(ann):
        origin = get_origin(ann)
        args = get_args(ann)
        # Handle primitives
        if ann == str:
            return {"type": "string"}
        elif ann == int:
            return {"type": "integer"}
        elif ann == float:
            return {"type": "number"}
        elif ann == bool:
            return {"type": "boolean"}
        # Handle list/array
        elif origin == list or origin == tuple or ann == list:
            item_type = args[0] if args else str
            return {"type": "array", "items": type_to_schema(item_type)}
        # Handle dict/object
        elif origin == dict or origin == TypingDict or ann == dict:
            # Accept any object
            return {"type": "object"}
        # Handle custom class with type annotations (dataclass or similar)
        elif hasattr(ann, "__annotations__"):
            props = {}
            reqs = []
            for k, v in ann.__annotations__.items():
                props[k] = type_to_schema(v)
                # No default detection for custom classes, assume required
                reqs.append(k)
            return {"type": "object", "properties": props, "required": reqs}
        # Fallback
        else:
            return {"type": "string"}

    for p in params:
        ann = p.annotation
        prop = type_to_schema(ann)
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
        properties[p.name] = prop

    # Extract description from run() docstring
    run_doc = cls.run.__doc__ or ""

    schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": run_doc.strip(),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
    cls.tool_schema = schema
    return cls

class ToolBase:
    """
    Base class for all tools. Subclasses should implement the `run` method.
    """
    name: str = None  # Optional: override in subclass

    def __init__(self, **kwargs):
        self.config = kwargs

    def run(self, *args, **kwargs) -> Any:
        """
        Main logic for the tool. Must be implemented by subclasses.
        """
        raise NotImplementedError("Tool must implement the run() method.")

def get_tools() -> list:
    """
    Returns a list of all registered tool schemas for LLM integration.
    """
    schemas = []
    for cls in tool_registry.values():
        if hasattr(cls, 'tool_schema'):
            schemas.append(cls.tool_schema)
    return schemas