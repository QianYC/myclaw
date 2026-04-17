"""File content/keyword search tool with ripgrep fallback."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from myclaw.tool_base import ToolBase, tool


def _has_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _search_with_ripgrep(
    pattern: str, directory: str, is_regex: bool, max_results: int
) -> str:
    """Use ripgrep for fast file content search."""
    cmd = ["rg", "--line-number", "--no-heading", "--color", "never"]
    if not is_regex:
        cmd.append("--fixed-strings")
    cmd.extend(["--max-count", str(max_results)])
    cmd.append(pattern)
    cmd.append(directory)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 1:
        return "No matches found."
    if result.returncode != 0:
        return f"ripgrep error: {result.stderr.strip()}"
    return result.stdout.strip()


def _search_with_python(
    pattern: str, directory: str, is_regex: bool, max_results: int
) -> str:
    """Fallback: walk directory tree and search file contents with Python."""
    compiled = re.compile(pattern if is_regex else re.escape(pattern), re.IGNORECASE)
    matches = []
    for root, _, files in os.walk(directory):
        for fname in files:
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        if compiled.search(line):
                            matches.append(f"{filepath}:{lineno}:{line.rstrip()}")
                            if len(matches) >= max_results:
                                return "\n".join(matches)
            except (OSError, PermissionError):
                continue
    if not matches:
        return "No matches found."
    return "\n".join(matches)


@tool
class FileSearchTool(ToolBase):
    """Search for content/keywords within files under a directory."""

    name = "file-search"

    # pylint: disable=arguments-differ
    def run(
        self, pattern: str, directory: str = ".", is_regex: bool = False, max_results: int = 50
    ) -> str:
        """
        Search for content/keywords in files within a directory.
        Uses ripgrep if available, otherwise falls back to Python built-in search.
        Args:
            pattern: The search pattern (plain text or regex).
            directory: The directory to search in (default: current directory).
            is_regex: Whether the pattern is a regex (default: False, plain text).
            max_results: Maximum number of matching lines to return (default: 50).
        Returns:
            Matching lines in format 'filepath:line_number:line_content'.
        """
        search_dir = str(Path(directory).expanduser().resolve())
        if not os.path.isdir(search_dir):
            return f"Directory not found: {search_dir}"

        if _has_ripgrep():
            print("[FileSearchTool] Using ripgrep.")
            return _search_with_ripgrep(pattern, search_dir, is_regex, max_results)
        print("[FileSearchTool] ripgrep not found, using Python fallback.")
        return _search_with_python(pattern, search_dir, is_regex, max_results)
