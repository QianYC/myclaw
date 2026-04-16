from myclaw.tool_base import ToolBase, tool
import subprocess
from typing import List
import platform
import shlex

@tool
class TerminalTool(ToolBase):
    name = "terminal-tool"

    def run(self, cmdlet: str, args: List[str]) -> str:
        """
        Executes a command with arguments securely in OS default terminal.
        Args:
            cmdlet: The command to run (e.g., 'ls', 'python').
            args: List of arguments (e.g., ['-l', '/home']).
        Returns:
            The output of the command (stdout + stderr).
        """
        try:
            system = platform.system()
            if system == "Windows":
                # Use PowerShell for Windows; quote each arg to handle spaces/special chars
                quoted_args = [f'"{a}"' if ' ' in a or '"' in a else a for a in args]
                shell_cmd = ["powershell.exe", "-Command", cmdlet] + quoted_args
            else:
                # Use bash for Unix-like systems; shlex.quote each part for safety
                safe_cmd = " ".join([shlex.quote(cmdlet)] + [shlex.quote(a) for a in args])
                shell_cmd = ["/bin/bash", "-c", safe_cmd]
            print(f"[TerminalTool] Running: {shell_cmd}")
            result = subprocess.run(shell_cmd, capture_output=True, text=True, check=False)
            output = f"return code: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            print("[TerminalTool] Execution completed.")
            return output.strip()
        except Exception as e:
            return f"[TerminalTool Error] {e}"
