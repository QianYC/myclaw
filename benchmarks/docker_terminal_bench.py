"""Docker-backed Terminal-Bench adapter.

Design:
  * Two pre-built base images contain myclaw + entrypoint: one derived from
    `ghcr.io/laude-institute/t-bench/ubuntu-24-04`, one from `python-3-13`.
    Built once via `ensure_base_images()`.
  * For each task, the task's own Dockerfile is read, its `FROM` line is
    rewritten to point at our myclaw-enabled base, and the result is built
    as `myclaw-tbench/task-<id>`.
  * We run the container with the task's prompt, tests/, and run-tests.sh
    attached. The container's entrypoint runs the agent, then the grader.
    Exit code 0 = pass.
  * Tasks whose base isn't one of the two supported ones are skipped (we
    yield nothing for them in `load_tasks`).

Everything runs in Docker. The host-side `AgentRunner` is ignored.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Iterable

import yaml

from .base import AgentRunner, Grade, RunResult, Task


REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent  # .../myclaw

# Maps substring in task's FROM line → our pre-built myclaw-enabled base tag.
BASE_IMAGE_MAP: dict[str, str] = {
    "laude-institute/t-bench/ubuntu-24-04": "myclaw-tbench/ubuntu-24-04-myclaw",
    "laude-institute/t-bench/python-3-13":  "myclaw-tbench/python-3-13-myclaw",
}

# Dockerfile templates we use to build those bases.
BASE_DOCKERFILES: dict[str, str] = {
    "myclaw-tbench/ubuntu-24-04-myclaw": "benchmarks/docker/Dockerfile.ubuntu-myclaw",
    "myclaw-tbench/python-3-13-myclaw":  "benchmarks/docker/Dockerfile.python-myclaw",
}


def _rewrite_localhost(url: str) -> str:
    """Rewrite localhost/127.0.0.1 endpoints so the container can reach the
    host-side LLM endpoint."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        new_netloc = parsed.netloc.replace(host, "host.docker.internal", 1)
        return urllib.parse.urlunparse(parsed._replace(netloc=new_netloc))
    return url


def _detect_base(dockerfile_text: str) -> str | None:
    """Find the first non-comment FROM line and return the mapped myclaw base
    image, or None if it doesn't match one of our supported bases."""
    for raw in dockerfile_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.upper().startswith("FROM"):
            continue
        for needle, base_tag in BASE_IMAGE_MAP.items():
            if needle in line:
                return base_tag
        return None  # first FROM wasn't a supported base — give up
    return None


def _rewrite_dockerfile(src_text: str, target_base_tag: str) -> str:
    """Replace the first non-comment `FROM` line with one pointing at our
    pre-built base. Preserves `AS name` aliases."""
    lines = src_text.splitlines()
    out: list[str] = []
    replaced = False
    from_re = re.compile(
        r"^(\s*FROM\s+)"              # group 1: FROM + whitespace
        r"(?:--platform=\S+\s+)?"     # optional --platform=...
        r"(\S+)"                      # group 2: image (replace this)
        r"(\s+AS\s+\S+)?\s*$",        # optional AS alias
        re.IGNORECASE,
    )
    for raw in lines:
        if not replaced and not raw.lstrip().startswith("#"):
            m = from_re.match(raw)
            if m:
                out.append(f"FROM {target_base_tag}{m.group(3) or ''}")
                replaced = True
                continue
        out.append(raw)
    if not replaced:
        raise RuntimeError("no FROM line found in task Dockerfile")
    return "\n".join(out) + "\n"


def _docker(*args: str, timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            f"docker {' '.join(args)} failed (rc={cp.returncode}):\n"
            f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
        )
    return cp


class DockerTerminalBench:
    name = "terminal-bench-docker"

    def __init__(
        self,
        tasks_root: Path,
        *,
        repo_root: Path | None = None,
        model: str,
        endpoint: str,
        api_key: str,
        max_turns: int = 50,
        task_timeout_s: int = 1800,
        keep_images: bool = False,
    ):
        self.tasks_root = Path(tasks_root).expanduser().resolve()
        # Accept either `.../original-tasks` or the repo root — our sibling
        # adapter does the same autodetection; reuse the logic informally.
        if not _looks_like_tasks_dir(self.tasks_root):
            for candidate in ("original-tasks", "tasks"):
                p = self.tasks_root / candidate
                if _looks_like_tasks_dir(p):
                    self.tasks_root = p
                    break
        if not _looks_like_tasks_dir(self.tasks_root):
            raise FileNotFoundError(
                f"Terminal-Bench tasks directory not found or empty: {self.tasks_root}"
            )

        self.repo_root = Path(repo_root).resolve() if repo_root else REPO_ROOT_DEFAULT
        self.model = model
        self.endpoint = _rewrite_localhost(endpoint)
        self.api_key = api_key
        self.max_turns = max_turns
        self.task_timeout_s = task_timeout_s
        self.keep_images = keep_images

        self._ensure_docker_available()
        self.ensure_base_images()

    # ---- base image management ------------------------------------------------

    @staticmethod
    def _ensure_docker_available() -> None:
        cp = _docker("version", "--format", "{{.Server.Version}}", check=False)
        if cp.returncode != 0:
            raise RuntimeError(
                "`docker` CLI not reachable. Start Docker Desktop (or the "
                f"daemon) and retry.\nstderr: {cp.stderr.strip()}"
            )

    def ensure_base_images(self) -> None:
        """Build the two myclaw-enabled base images if they don't already exist."""
        for tag, dockerfile_rel in BASE_DOCKERFILES.items():
            existing = _docker("image", "inspect", tag, check=False)
            if existing.returncode == 0:
                print(f"[docker-bench] base {tag} already present")
                continue
            dockerfile_abs = self.repo_root / dockerfile_rel
            if not dockerfile_abs.is_file():
                raise FileNotFoundError(f"base dockerfile missing: {dockerfile_abs}")
            print(f"[docker-bench] building base image {tag} from {dockerfile_rel}...")
            _docker(
                "build",
                "-f", str(dockerfile_abs),
                "-t", tag,
                str(self.repo_root),
                timeout=1800,
            )
            print(f"[docker-bench] built {tag}")

    # ---- task iteration -------------------------------------------------------

    def load_tasks(self, limit: int | None = None) -> Iterable[Task]:
        """Yield tasks whose base image we support. Unsupported bases are
        silently skipped so `--limit N` always returns N actually-runnable
        tasks rather than a mix of skips and runs."""
        count = 0
        for task_dir in sorted(self.tasks_root.iterdir()):
            if not task_dir.is_dir():
                continue
            dockerfile = task_dir / "Dockerfile"
            task_yaml = task_dir / "task.yaml"
            tests_dir = task_dir / "tests"
            run_tests = task_dir / "run-tests.sh"
            if not (dockerfile.exists() and task_yaml.exists()
                    and tests_dir.is_dir() and run_tests.exists()):
                continue
            try:
                spec = yaml.safe_load(task_yaml.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            instruction = spec.get("instruction") or spec.get("prompt")
            if not instruction:
                continue
            base_tag = _detect_base(dockerfile.read_text(encoding="utf-8"))
            if base_tag is None:
                continue  # unsupported base — skip quietly
            yield Task(
                id=task_dir.name,
                prompt=instruction,
                workspace=None,
                metadata={
                    "task_dir": str(task_dir),
                    "base_tag": base_tag,
                    "difficulty": spec.get("difficulty"),
                    "category": spec.get("category"),
                    "tags": spec.get("tags") or [],
                    "max_test_timeout_sec": spec.get("max_test_timeout_sec"),
                    "max_agent_timeout_sec": spec.get("max_agent_timeout_sec"),
                },
            )
            count += 1
            if limit is not None and count >= limit:
                return

    # ---- per-task run ---------------------------------------------------------

    async def run_task(self, task: Task, agent: AgentRunner) -> RunResult:
        """The `agent` argument is unused: the agent runs inside the container."""
        del agent
        task_dir = Path(task.metadata["task_dir"])
        base_tag = task.metadata["base_tag"]
        image_tag = f"myclaw-tbench/task-{task.id}"

        t0 = time.time()
        try:
            self._build_task_image(task_dir, base_tag, image_tag)
        except Exception as exc:
            return RunResult(
                output="", turns=0, tool_calls=[], tokens_in=0, tokens_out=0,
                cost_usd=0.0, duration_s=time.time() - t0,
                error=f"build failed: {exc}",
            )

        # Workspace holds the prompt + test artifacts the container mounts.
        stage = Path(tempfile.mkdtemp(prefix=f"tbench-stage-{task.id}-"))
        try:
            (stage / "task-prompt.txt").write_text(task.prompt, encoding="utf-8")
            return await self._run_container(task, image_tag, stage, task_dir, t0)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            if not self.keep_images:
                _docker("image", "rm", "-f", image_tag, check=False)

    def _build_task_image(self, task_dir: Path, base_tag: str, image_tag: str) -> None:
        src_dockerfile = (task_dir / "Dockerfile").read_text(encoding="utf-8")
        rewritten = _rewrite_dockerfile(src_dockerfile, base_tag)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".Dockerfile", delete=False, encoding="utf-8"
        )
        try:
            tmp.write(rewritten)
            tmp.close()
            print(f"[docker-bench] building task image {image_tag}...")
            _docker(
                "build",
                "-f", tmp.name,
                "-t", image_tag,
                str(task_dir),
                timeout=1200,
            )
        finally:
            os.unlink(tmp.name)

    async def _run_container(
        self,
        task: Task,
        image_tag: str,
        stage: Path,
        task_dir: Path,
        t0: float,
    ) -> RunResult:
        container_name = f"myclaw-tbench-{task.id}-{int(time.time())}"
        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--add-host=host.docker.internal:host-gateway",
            "-v", f"{(stage / 'task-prompt.txt').as_posix()}:/myclaw/task-prompt.txt:ro",
            "-v", f"{(task_dir / 'run-tests.sh').as_posix()}:/myclaw/run-tests.sh:ro",
            "-v", f"{(task_dir / 'tests').as_posix()}:/myclaw/tests:ro",
            "-e", f"MYCLAW_MODEL={self.model}",
            "-e", f"MYCLAW_ENDPOINT={self.endpoint}",
            "-e", f"MYCLAW_API_KEY={self.api_key}",
            "-e", f"MYCLAW_MAX_TURNS={self.max_turns}",
            "-e", "TEST_DIR=/myclaw/tests",
            image_tag,
        ]
        print(f"[docker-bench] running container for task {task.id}...")
        try:
            cp = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.task_timeout_s,
            )
            stdout, stderr, returncode, timed_out = cp.stdout, cp.stderr, cp.returncode, False
        except subprocess.TimeoutExpired as exc:
            _docker("kill", container_name, check=False)
            stdout = (exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
            stderr = (exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
            returncode = None
            timed_out = True

        run_summary = _parse_run_summary(stdout)
        error = None
        if timed_out:
            error = f"task timeout after {self.task_timeout_s}s"
        elif returncode is None:
            error = "container produced no exit code"
        elif returncode != 0:
            # Container ran but agent+grader chain returned non-zero.
            # Encode the exit code here so grade() can distinguish this
            # (task-level failure) from host-side errors.
            error = f"container_exit_code={returncode}"

        return RunResult(
            output=stdout[-4000:] + ("\n[stderr tail]\n" + stderr[-2000:] if stderr else ""),
            turns=run_summary.get("turns", 0),
            tool_calls=run_summary.get("tool_calls", []),
            tokens_in=run_summary.get("tokens_in", 0),
            tokens_out=run_summary.get("tokens_out", 0),
            cost_usd=0.0,  # local endpoint; plug in a price table if you run against a paid API
            duration_s=time.time() - t0,
            error=error,
        )

    # ---- grading --------------------------------------------------------------

    def grade(self, task: Task, result: RunResult) -> Grade:
        """Exit code-based grading: container returned 0 iff both the agent
        and the grader succeeded. Anything else is a FAIL. `result.error`
        carries either a host-side problem or `container_exit_code=N`."""
        if result.error is None:
            return Grade(
                passed=True,
                score=1.0,
                details={"stdout_tail": result.output[-800:]},
            )
        return Grade(
            passed=False,
            score=0.0,
            details={
                "error": result.error,
                "stdout_tail": result.output[-800:],
            },
        )


# ---- helpers --------------------------------------------------------------


def _looks_like_tasks_dir(p: Path) -> bool:
    if not p.is_dir():
        return False
    for child in p.iterdir():
        if child.is_dir() and (child / "task.yaml").exists():
            return True
    return False


_RUN_SUMMARY_RE = re.compile(r"##MYCLAW_RUN_RESULT##(.*?)##END##", re.DOTALL)


def _parse_run_summary(stdout: str) -> dict:
    """Extract the JSON summary the in-container agent_runner.py prints."""
    m = _RUN_SUMMARY_RE.search(stdout)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
