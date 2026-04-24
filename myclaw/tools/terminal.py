"""Cross-platform terminal command execution tool."""

import os
import platform
import shlex
import signal
import subprocess
from typing import List

from myclaw.tool_base import ToolBase, tool


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill `process` and all of its descendants. Best-effort.

    `subprocess.Popen.kill()` only terminates the immediate child on Windows,
    leaving grandchildren orphaned with the stdout pipe still open, which is
    what causes `communicate()` to hang on timeout.
    """
    if process.poll() is not None:
        return
    try:
        if platform.system() == "Windows":
            # taskkill with /T walks the job tree; /F is SIGKILL-equivalent.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        else:
            # child was started with start_new_session=True, so its PID is the
            # process-group leader — killpg reaches every descendant.
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
        pass


@tool
class TerminalTool(ToolBase):
    """Execute a command with arguments in the host's default shell."""

    name = "terminal-tool"

    DEFAULT_TIMEOUT_S = 60
    DRAIN_TIMEOUT_S = 5

    # pylint: disable=arguments-differ
    def run(self, cmdlet: str, args: List[str], timeout_s: int = DEFAULT_TIMEOUT_S) -> str:
        """
        Executes a command with arguments securely in OS default terminal.
        Args:
            cmdlet: The command to run (e.g., 'ls', 'python').
            args: List of arguments (e.g., ['-l', '/home']).
            timeout_s: Kill the command and its descendants after this many
                seconds. Default 60.
        Returns:
            The output of the command (stdout + stderr), or a timeout message.
        """
        system = platform.system()
        if system == "Windows":
            quoted_args = [f'"{a}"' if ' ' in a or '"' in a else a for a in args]
            shell_cmd = ["powershell.exe", "-Command", cmdlet] + quoted_args
            popen_kwargs = {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
            }
        else:
            safe_cmd = " ".join([shlex.quote(cmdlet)] + [shlex.quote(a) for a in args])
            shell_cmd = ["/bin/bash", "-c", safe_cmd]
            # Puts child into its own process group so killpg reaches all
            # descendants on timeout.
            popen_kwargs = {"start_new_session": True}

        print(f"[TerminalTool] Running: {shell_cmd} (timeout={timeout_s}s)")

        process = subprocess.Popen(
            shell_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen_kwargs,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
            returncode = process.returncode
            print("[TerminalTool] Execution completed.")
            return (
                f"return code: {returncode}\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            ).strip()
        except subprocess.TimeoutExpired:
            print(f"[TerminalTool] Timed out after {timeout_s}s. Killing process tree.")
            _kill_tree(process)
            # Drain whatever the pipes hold now that the tree is dead. Bound
            # this tightly so we can't hang here either.
            try:
                stdout, stderr = process.communicate(timeout=self.DRAIN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                # Pipes still held open somehow (e.g., detached WSL grandchildren).
                # Give up on capturing output rather than blocking further.
                _kill_tree(process)
                stdout, stderr = "", "[drain timed out — output discarded]"
            return (
                f"return code: TIMEOUT after {timeout_s}s\n"
                f"stdout:\n{stdout or ''}\n"
                f"stderr:\n{stderr or ''}"
            ).strip()
