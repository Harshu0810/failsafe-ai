"""
executor.py
Runs arbitrary Python source code inside a child subprocess with:
  • strict wall-clock timeout (default 8 s)
  • captured stdout + stderr
  • graceful SIGTERM / SIGKILL on timeout
  • no network or file-system escape heuristics (suitable for portfolio demos)

The module intentionally avoids exec() / eval() in the main process so a
runaway script cannot affect the parent Streamlit app.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    """Structured result returned by Executor.run()."""

    injection_name: str = ""
    scenario: str = ""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    timed_out: bool = False
    execution_time_ms: float = 0.0

    # Derived fields filled by the analyzer
    error_type: str = ""       # e.g. "NameError"
    error_message: str = ""    # first line of the traceback
    traceback: str = ""        # full traceback text

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict:
        return {
            "injection_name": self.injection_name,
            "scenario": self.scenario,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "success": self.success,
        }


class Executor:
    """
    Executes a Python script string safely in a subprocess.

    Parameters
    ----------
    timeout_seconds : int
        Hard wall-clock limit. The process is killed when exceeded.
        Default: 8 s (generous for simple scripts, tight enough to prevent hangs).
    python_executable : str
        Path to the Python interpreter. Defaults to the same interpreter running
        this process (sys.executable).
    """

    def __init__(
        self,
        timeout_seconds: int = 8,
        python_executable: str | None = None,
    ):
        self.timeout = timeout_seconds
        self.python = python_executable or sys.executable

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        source: str,
        injection_name: str = "",
        scenario: str = "",
    ) -> ExecutionResult:
        """
        Write *source* to a temp file, execute it in a child process,
        and return a fully-populated ExecutionResult.
        """
        result = ExecutionResult(
            injection_name=injection_name,
            scenario=scenario,
        )

        # Write source to a temporary .py file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="failsafe_",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(source)
            tmp_path = tmp.name

        try:
            result = self._execute(tmp_path, result)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return result

    def run_csv_script(
        self,
        csv_source: str,
        csv_bytes: bytes,
        injection_name: str = "",
        scenario: str = "",
    ) -> ExecutionResult:
        """
        Run a script that reads a CSV file.  The mutated CSV is written to a
        temp file and its path is injected as the variable ``INPUT_CSV`` at the
        top of the script before execution.
        """
        with tempfile.NamedTemporaryFile(
            suffix=".csv",
            prefix="failsafe_csv_",
            delete=False,
        ) as csv_tmp:
            csv_tmp.write(csv_bytes)
            csv_path = csv_tmp.name

        patched_source = (
            f'INPUT_CSV = r"{csv_path}"\n'
            "import pandas as _pd\n"
            "_df = _pd.read_csv(INPUT_CSV)\n\n"
        ) + csv_source

        try:
            return self.run(patched_source, injection_name, scenario)
        finally:
            try:
                os.unlink(csv_path)
            except OSError:
                pass

    def run_project(
        self,
        files: dict[str, bytes],
        entry_point: str,
        injection_name: str = "",
        scenario: str = "",
    ) -> ExecutionResult:
        """
        Write *files* (mapping of filename → bytes) to a temporary directory,
        install any ``requirements.txt`` found, then execute *entry_point*.

        Parameters
        ----------
        files : dict[str, bytes]
            All uploaded files.  Keys are filenames (basename only).
        entry_point : str
            Filename of the script to execute (must be a key in *files*).
        injection_name / scenario : str
            Passed through to ExecutionResult for reporting.
        """
        import shutil

        result = ExecutionResult(
            injection_name=injection_name,
            scenario=scenario,
        )

        tmpdir = tempfile.mkdtemp(prefix="failsafe_proj_")
        try:
            # 1 — Write all files into the temp directory
            for fname, data in files.items():
                dest = os.path.join(tmpdir, fname)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                mode = "w" if isinstance(data, str) else "wb"
                with open(dest, mode) as fh:
                    fh.write(data)

            # 2 — Install requirements if present
            req_path = os.path.join(tmpdir, "requirements.txt")
            if os.path.exists(req_path):
                try:
                    pip_proc = subprocess.run(
                        [self.python, "-m", "pip", "install", "-r", req_path,
                         "--quiet", "--disable-pip-version-check", "--no-input"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=120,
                        text=True,
                    )
                    if pip_proc.returncode != 0:
                        # Surface pip errors into the result so they appear in the
                        # failure analyser rather than silently crashing later
                        result.stderr = (
                            "[FAILSAFE] pip install failed:\n" + pip_proc.stderr
                        )
                        result.exit_code = pip_proc.returncode
                        result.error_type = "ModuleNotFoundError"
                        result.error_message = "Dependency installation failed."
                        result.traceback = result.stderr
                        return result
                except subprocess.TimeoutExpired:
                    result.stderr = (
                        "[FAILSAFE] pip install timed out after 120 s.\n"
                        "Tip: pre-install heavy packages in your virtual environment "
                        "and omit them from the uploaded requirements.txt, "
                        "or only list lightweight packages."
                    )
                    result.exit_code = -1
                    result.error_type = "TimeoutError"
                    result.error_message = "pip install exceeded the 120 s sandbox limit."
                    result.traceback = result.stderr
                    return result

            # 3 — Execute the entry point inside the project directory
            entry_abs = os.path.join(tmpdir, entry_point)
            result = self._execute_in_dir(entry_abs, tmpdir, result)

        finally:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _execute(self, script_path: str, result: ExecutionResult) -> ExecutionResult:
        """Fork a child process and wait up to self.timeout seconds."""
        t0 = time.perf_counter()

        try:
            proc = subprocess.run(
                [self.python, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                timeout=self.timeout,
                text=True,
                env=os.environ.copy(),
            )
            result.stdout = proc.stdout.strip()
            result.stderr = proc.stderr.strip()
            result.exit_code = proc.returncode

        except subprocess.TimeoutExpired as exc:
            result.timed_out = True
            result.exit_code = -1
            result.stdout = (exc.stdout or b"").decode(errors="replace").strip()
            result.stderr = (exc.stderr or b"").decode(errors="replace").strip()
            result.stderr += "\n[SANDBOX] Process killed — execution timeout exceeded."

        result.execution_time_ms = (time.perf_counter() - t0) * 1000

        # Parse traceback info from stderr
        result.traceback = result.stderr
        result.error_type, result.error_message = _parse_error(result.stderr)

        return result

    def _execute_in_dir(
        self,
        script_path: str,
        cwd: str,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """Like _execute, but sets the working directory to *cwd* so that
        relative imports and file reads inside the project resolve correctly."""
        t0 = time.perf_counter()

        env = os.environ.copy()
        env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")

        try:
            proc = subprocess.run(
                [self.python, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                timeout=self.timeout,
                text=True,
                cwd=cwd,
                env=env,
            )
            result.stdout = proc.stdout.strip()
            result.stderr = proc.stderr.strip()
            result.exit_code = proc.returncode

        except subprocess.TimeoutExpired as exc:
            result.timed_out = True
            result.exit_code = -1
            result.stdout = (exc.stdout or b"").decode(errors="replace").strip()
            result.stderr = (exc.stderr or b"").decode(errors="replace").strip()
            result.stderr += "\n[SANDBOX] Process killed — execution timeout exceeded."

        result.execution_time_ms = (time.perf_counter() - t0) * 1000
        result.traceback = result.stderr
        result.error_type, result.error_message = _parse_error(result.stderr)
        return result


def _parse_error(stderr: str) -> tuple[str, str]:
    """
    Extract (error_type, error_message) from a Python traceback string.
    Returns ("", "") if no recognisable error is found.
    """
    if not stderr:
        return "", ""

    lines = stderr.strip().splitlines()
    # The last non-empty line of a Python traceback is usually "ErrorType: message"
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        # Match "SomeError: description" or bare "SomeError"
        m = re.match(
            r"^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|Interrupt)?)\s*(?::\s*(.*))?$",
            line,
        )
        if m:
            return m.group(1), (m.group(2) or "").strip()
        # Handle "[SANDBOX] Process killed …"
        if "[SANDBOX]" in line:
            return "TimeoutError", "Execution exceeded the sandbox time limit."

    return "UnknownError", lines[-1] if lines else ""
