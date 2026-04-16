"""
Base class and class-level decorator for defining tools in a structured way.
"""

import inspect
from typing import Any, Dict, Type, get_origin, get_args

# Registry to keep track of all tool classes
tool_registry: Dict[str, Type['ToolBase']] = {}


_PRIMITIVE_SCHEMAS = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
}


def _type_to_schema(ann):
    """Convert a Python type annotation to a JSON-schema fragment."""
    if ann in _PRIMITIVE_SCHEMAS:
        return _PRIMITIVE_SCHEMAS[ann]
    origin = get_origin(ann)
    args = get_args(ann)
    # Handle list/tuple/array
    if origin in (list, tuple) or ann is list:
        item_type = args[0] if args else str
        return {"type": "array", "items": _type_to_schema(item_type)}
    # Handle dict/object
    if origin is dict or ann is dict or origin is Dict:
        return {"type": "object"}
    # Handle custom class with type annotations (dataclass or similar)
    if hasattr(ann, "__annotations__"):
        props = {}
        reqs = []
        for k, v in ann.__annotations__.items():
            props[k] = _type_to_schema(v)
            # No default detection for custom classes, assume required
            reqs.append(k)
        return {"type": "object", "properties": props, "required": reqs}
    # Fallback
    return {"type": "string"}


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

    for p in params:
        prop = _type_to_schema(p.annotation)
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
    tool_schema: Dict[str, Any] = None

    def __init__(self, **kwargs):
        self.config = kwargs

    def run(self, *args, **kwargs) -> Any:
        """
        Main logic for the tool. Must be implemented by subclasses.
        """
        raise NotImplementedError("Tool must implement the run() method.")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Return a configuration value provided at construction time."""
        return self.config.get(key, default)


def get_tools() -> list:
    """
    Returns a list of all registered tool schemas for LLM integration.
    """
    schemas = []
    for cls in tool_registry.values():
        if hasattr(cls, 'tool_schema') and cls.tool_schema is not None:
            schemas.append(cls.tool_schema)
    return schemas
