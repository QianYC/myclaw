"""Glob tool for finding files/paths by glob pattern."""

from pathlib import Path

from myclaw.tool_base import ToolBase, tool


@tool
class GlobTool(ToolBase):
    """Find files and directories matching a shell-style glob pattern."""

    name = "glob"

    # pylint: disable=arguments-differ,too-many-arguments,too-many-positional-arguments
    def run(
        self,
        pattern: str,
        directory: str = ".",
        recursive: bool = True,
        max_results: int = 100,
        sort_by_mtime: bool = True,
    ) -> str:
        """
        Find files and directories matching a glob pattern.
        Supports standard glob syntax (`*`, `?`, `[abc]`) and `**` for recursive matching.
        Args:
            pattern: The glob pattern to match (e.g., '*.py', '**/*.md', 'src/**/test_*.py').
            directory: The base directory to search in (default: current directory).
            recursive: If True and the pattern does not contain '**', '**/' is
                prepended so matching descends into subdirectories (default: True).
            max_results: Maximum number of paths to return (default: 100).
            sort_by_mtime: If True, sort results by modification time (newest first).
                Otherwise sort alphabetically (default: True).
        Returns:
            A newline-separated list of matching absolute paths, or a message if none found.
        """
        base = Path(directory).expanduser().resolve()
        if not base.is_dir():
            return f"Directory not found: {base}"

        effective_pattern = pattern
        if recursive and "**" not in pattern:
            effective_pattern = f"**/{pattern}"

        try:
            matches = list(base.glob(effective_pattern))
        except (OSError, ValueError) as e:
            return f"Invalid glob pattern '{pattern}': {e}"

        if not matches:
            return f"No matches found for pattern '{pattern}' in {base}."

        if sort_by_mtime:
            def _mtime(p: Path) -> float:
                try:
                    return p.stat().st_mtime
                except OSError:
                    return 0.0
            matches.sort(key=_mtime, reverse=True)
        else:
            matches.sort(key=str)

        truncated = matches[:max_results]
        lines = [str(p) for p in truncated]

        if len(matches) > max_results:
            lines.append(
                f"... ({len(matches) - max_results} more results truncated; "
                f"increase max_results to see more)"
            )
        return "\n".join(lines)
