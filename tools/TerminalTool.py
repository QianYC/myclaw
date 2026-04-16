from tool_base import ToolBase, tool
import subprocess
from typing import List
import platform

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
            print(f"[TerminalTool] Running: {cmdlet} {' '.join(args)}")
            system = platform.system()
            if system == "Windows":
                # Use PowerShell for Windows
                shell_cmd = ["powershell.exe", cmdlet] + args
            else:
                # Use bash for Unix-like systems
                shell_cmd = ["/bin/bash", "-c", " ".join([cmdlet] + args)]
            result = subprocess.run(shell_cmd, capture_output=True, text=True, check=False)
            output = f"return code: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            return output.strip()
        except Exception as e:
            return f"[TerminalTool Error] {e}"
