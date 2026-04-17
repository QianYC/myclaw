"""File CRUD tool for reading, writing, creating, and deleting files."""

import os
from pathlib import Path
from typing import Literal

from myclaw.tool_base import ToolBase, tool


@tool
class FileTool(ToolBase):
    """Perform read/write/append/delete operations on a single file path."""

    name = "file"

    # pylint: disable=arguments-differ
    def run(
        self,
        action: Literal["read", "write", "append", "delete"],
        path: str,
        content: str = "",
    ) -> str:
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

        if action in ("write", "append"):
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "w" if action == "write" else "a"
            with open(target, mode, encoding="utf-8") as f:
                f.write(content)
            verb = "Written" if action == "write" else "Appended"
            return f"{verb} {len(content)} chars to {target}"

        if action == "delete":
            if not target.exists():
                return f"File not found: {target}"
            os.remove(target)
            return f"Deleted {target}"

        return f"Unknown action '{action}'. Use one of: read, write, append, delete."
