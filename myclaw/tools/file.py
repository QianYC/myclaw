"""File CRUD tool for reading, writing, creating, and deleting files."""

import os
from pathlib import Path
from typing import Literal

from myclaw.tool_base import ToolBase, tool


@tool
class FileTool(ToolBase):
    name = "file"

    def run(self, action: Literal["read", "write", "append", "delete"], path: str, content: str = "") -> str:
        """
        Perform file operations: read, write, append, or delete.
        Args:
            action: The operation to perform. One of 'read', 'write', 'append', 'delete'.
            path: The absolute or relative file path.
            content: The content to write or append (ignored for read/delete).
        Returns:
            The file content (for read), or a confirmation message.
        """
        target = Path(path).expanduser().resolve()

        if action == "read":
            if not target.is_file():
                return f"File not found: {target}"
            return target.read_text(encoding="utf-8")

        elif action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Written {len(content)} chars to {target}"

        elif action == "append":
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Appended {len(content)} chars to {target}"

        elif action == "delete":
            if not target.exists():
                return f"File not found: {target}"
            os.remove(target)
            return f"Deleted {target}"

        else:
            return f"Unknown action '{action}'. Use one of: read, write, append, delete."
