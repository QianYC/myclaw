import subprocess
import shlex

from myclaw.tool_base import ToolBase, tool

@tool
class GitTool(ToolBase):
    """Tool for executing Git commands in the terminal."""

    name = "git-tool"

    # pylint: disable=arguments-differ
    def run(self, args: list[str]) -> str:
        """
        Executes a git command with arguments securely in the terminal.
        This tool takes precedence over the TerminalTool for git commands, allowing for better error handling and output formatting.

        Args:
            args: List of git command arguments (e.g., ['status', '-s']).
        Returns:
            The output of the git command (stdout + stderr).
        """
        safe_cmd = "git " + " ".join(shlex.quote(a) for a in args)
        print(f"[GitTool] Running: {safe_cmd}")
        result = subprocess.run(safe_cmd, capture_output=True, text=True, shell=True, check=False)
        output = (
            f"return code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        print("[GitTool] Execution completed.")
        return output.strip()