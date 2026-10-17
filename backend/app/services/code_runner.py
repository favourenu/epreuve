"""Runs candidate Python code against test cases in a separate, locked-down process.

Defence in depth, designed to work on hosts without containers (e.g. free web
services), in layers:

1. A separate process with a scrubbed environment: no SECRET_KEY, API keys or
   database URL is visible to submitted code. Python runs isolated (-I).
2. Python audit hooks inside that process block opening files (except reading
   the standard library), listing directories, network sockets, starting
   processes, and ctypes.
3. On Linux, resource limits cap CPU time, memory, output size and open files,
   and the process runs in its own session so it can be killed as a group.
4. Output goes to size-capped files, never an unbounded pipe, and a wall-clock
   timeout applies everywhere.

Audit hooks are not a perfect security boundary (CPython's own docs say so), so
this raises the bar a lot rather than making escape impossible. For untrusted
public traffic at scale, run the runner in a container or microVM as well.
"""

import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings

_HARNESS = r'''
import contextlib, copy, io, json, linecache, math, os, sys, traceback


def apply_limits(cfg):
    """Lower this process's resource limits (Linux/macOS). Code can't raise them again."""
    try:
        import resource
    except ImportError:  # Windows: rely on the wall-clock timeout
        return
    mb = 1024 * 1024
    limits = {
        resource.RLIMIT_CPU: cfg["cpu_seconds"],
        resource.RLIMIT_AS: cfg["memory_mb"] * mb,
        resource.RLIMIT_FSIZE: cfg["output_bytes"],
        resource.RLIMIT_NOFILE: 64,
        resource.RLIMIT_CORE: 0,
    }
    for res, value in limits.items():
        try:
            resource.setrlimit(res, (value, value))
        except (ValueError, OSError):
            pass


BLOCKED_EVENTS = {
    "os.system": "Running shell commands",
    "os.exec": "Starting programs",
    "os.posix_spawn": "Starting programs",
    "os.spawn": "Starting programs",
    "os.fork": "Starting processes",
    "os.forkpty": "Starting processes",
    "os.startfile": "Starting programs",
    "subprocess.Popen": "Starting programs",
    "os.kill": "Sending signals",
    "os.killpg": "Sending signals",
    "socket.__new__": "Network access",
    "socket.connect": "Network access",
    "socket.bind": "Network access",
    "socket.getaddrinfo": "Network access",
    "socket.gethostbyname": "Network access",
    "glob.glob": "Listing directories",
    "os.chdir": "Changing directory",
    "os.remove": "Deleting files",
    "os.rmdir": "Deleting files",
    "shutil.rmtree": "Deleting files",
    "os.rename": "Moving files",
    "os.mkdir": "Creating directories",
    "os.chmod": "Changing file permissions",
    "os.chown": "Changing file permissions",
    "os.truncate": "Changing files",
    "os.link": "Creating links",
    "os.symlink": "Creating links",
    "os.utime": "Changing files",
    "os.putenv": "Changing the environment",
    "os.unsetenv": "Changing the environment",
    "webbrowser.open": "Opening a browser",
}
BLOCKED_PREFIXES = ("ctypes.", "winreg.", "_winapi.", "msvcrt.")
# Importing socket is harmless (stdlib modules like email.utils do it); using it is
# blocked by the socket.* events above. These modules, though, can bypass the hooks.
BLOCKED_MODULES = {"ctypes", "_ctypes", "cffi", "_posixsubprocess", "_winapi", "winreg", "msvcrt", "multiprocessing"}


def install_guard():
    roots = tuple(sorted({os.path.realpath(p) + os.sep for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix)}))

    def deny(what):
        raise PermissionError(f"{what} is disabled in the code runner.")

    def inside_python(path):
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        real = os.path.realpath(os.fspath(path))
        return real.startswith(roots) or real + os.sep in roots

    def hook(event, args):
        if event in BLOCKED_EVENTS:
            deny(BLOCKED_EVENTS[event])
        if event.startswith(BLOCKED_PREFIXES):
            deny("Low-level system access")
        if event == "import" and args[0].split(".")[0] in BLOCKED_MODULES:
            deny(f"Importing '{args[0]}'")
        if event in ("os.listdir", "os.scandir"):
            # The import system lists package folders to find submodules, so allow
            # that inside the Python installation only.
            path = args[0] if args and args[0] is not None else "."
            if isinstance(path, int) or not inside_python(path):
                deny("Listing directories")
        if event == "open":
            path, mode = args[0], args[1] if len(args) > 1 else "r"
            if isinstance(path, int):
                if path > 2:
                    deny("Opening files")
                return
            if any(c in (mode or "r") for c in "wax+"):
                deny("Writing files")
            if not inside_python(path):
                deny("Opening files")

    sys.addaudithook(hook)


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def user_frames(exc):
    return [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == "solution.py"]


def last_line(exc):
    message = "".join(traceback.format_exception_only(type(exc), exc)).strip().splitlines()[-1]
    frames = user_frames(exc)
    return f"{message} (line {frames[-1].lineno})" if frames else message


def describe(exc):
    """A traceback showing only the candidate's own code, not this harness."""
    if isinstance(exc, SyntaxError):
        return "".join(traceback.format_exception_only(type(exc), exc)).strip()
    frames = user_frames(exc)
    head = "Traceback (most recent call last):\n" + "".join(traceback.format_list(frames)) if frames else ""
    return (head + "".join(traceback.format_exception_only(type(exc), exc))).strip()


def main():
    spec_path, marker = sys.argv[1], sys.argv[2]
    del sys.argv[1:]  # don't leave the marker lying around for submitted code
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    real_stdout = sys.__stdout__
    max_out = spec["max_output"]

    def emit(payload):
        real_stdout.write(marker + json.dumps(payload) + "\n")
        real_stdout.flush()

    apply_limits(spec["limits"])
    # Lets tracebacks show the candidate's source lines for the virtual solution.py file.
    linecache.cache["solution.py"] = (len(spec["code"]), None, spec["code"].splitlines(True), "solution.py")
    install_guard()

    namespace = {"__name__": "solution"}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(spec["code"], "solution.py", "exec"), namespace)
    except BaseException as exc:
        emit({"error": describe(exc)})
        return

    fn = namespace.get(spec["function_name"])
    if not callable(fn):
        emit({"error": f"Function '{spec['function_name']}' is not defined. Keep the function name from the starter code."})
        return

    results = []
    for test in spec["tests"]:
        out = io.StringIO()
        entry = {"passed": False, "output": None, "error": None, "stdout": ""}
        try:
            with contextlib.redirect_stdout(out):
                got = fn(*copy.deepcopy(test["args"]))
            try:
                got = json.loads(json.dumps(got))
            except (TypeError, ValueError):
                got = repr(got)
            entry["output"] = got
            entry["passed"] = same(got, test["expected"])
        except BaseException as exc:
            entry["error"] = last_line(exc)
        entry["stdout"] = out.getvalue()[:max_out]
        results.append(entry)

    emit({"error": None, "results": results})


main()
'''


@dataclass
class TestOutcome:
    args: list[Any]
    expected: Any
    hidden: bool
    passed: bool
    output: Any = None
    error: str | None = None
    stdout: str = ""

    def public(self) -> dict[str, Any]:
        """Hidden tests reveal only whether they passed, like real assessment platforms."""
        if self.hidden:
            return {"hidden": True, "passed": self.passed, "error": "Failed" if self.error else None}
        return {
            "hidden": False,
            "passed": self.passed,
            "args": self.args,
            "expected": self.expected,
            "output": self.output,
            "error": self.error,
            "stdout": self.stdout,
        }


@dataclass
class RunResult:
    outcomes: list[TestOutcome]
    error: str | None = None  # syntax error, missing function, timeout, crash
    timed_out: bool = False

    @property
    def passed(self) -> int:
        return sum(o.passed for o in self.outcomes)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    def public(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "timed_out": self.timed_out,
            "passed": self.passed,
            "total": self.total,
            "tests": [o.public() for o in self.outcomes],
        }


def _child_env() -> dict[str, str]:
    """A minimal environment: nothing from the server's own (secrets, keys, DB URL)."""
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
    if os.name == "nt":  # Python can't start on Windows without these
        for key in ("SYSTEMROOT", "WINDIR"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def _read_capped(path: Path, limit: int) -> str:
    with open(path, "rb") as f:
        return f.read(limit).decode("utf-8", errors="replace")


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)  # the whole session, not just the child
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass
    proc.wait()


@lru_cache
def _run_slots() -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(get_settings().code_max_concurrent_runs)


def run_tests(code: str, function_name: str, tests: list[dict[str, Any]]) -> RunResult:
    """Run `code` and call `function_name` with each test's args.

    `tests` items: {"args": [...], "expected": ..., "hidden": bool}.
    At most `code_max_concurrent_runs` run at once, so a burst of submissions
    can't exhaust a small server's memory.
    """
    slots = _run_slots()
    if not slots.acquire(timeout=get_settings().code_queue_wait_seconds):
        return RunResult(
            outcomes=[TestOutcome(t["args"], t["expected"], t.get("hidden", False), False) for t in tests],
            error="The code runner is busy right now. Please try again in a moment.",
        )
    try:
        return _run_tests(code, function_name, tests)
    finally:
        slots.release()


def _run_tests(code: str, function_name: str, tests: list[dict[str, Any]]) -> RunResult:
    settings = get_settings()
    timeout = settings.code_run_timeout_seconds
    output_cap = settings.code_output_limit_bytes

    def failed_all(error: str, timed_out: bool = False) -> RunResult:
        return RunResult(
            outcomes=[TestOutcome(t["args"], t["expected"], t.get("hidden", False), False) for t in tests],
            error=error,
            timed_out=timed_out,
        )

    marker = f"__RESULT_{secrets.token_hex(16)}__"
    spec = {
        "code": code,
        "function_name": function_name,
        "tests": [{"args": t["args"], "expected": t["expected"]} for t in tests],
        "max_output": 2000,
        "limits": {
            "cpu_seconds": int(timeout) + 1,
            "memory_mb": settings.code_memory_limit_mb,
            "output_bytes": output_cap,
        },
    }
    with tempfile.TemporaryDirectory(prefix="epreuve-run-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "harness.py").write_text(_HARNESS, encoding="utf-8")
        (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        out_path, err_path = tmp_path / "stdout.txt", tmp_path / "stderr.txt"
        with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-X", "utf8", "harness.py", "spec.json", marker],
                cwd=tmp,
                env=_child_env(),
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                start_new_session=os.name == "posix",
            )
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill(proc)
                return failed_all(
                    f"Time limit exceeded ({timeout:g}s). Check for infinite loops or an inefficient algorithm.",
                    timed_out=True,
                )
        flooded = out_path.stat().st_size >= output_cap
        stdout = _read_capped(out_path, output_cap + 1024)
        stderr = _read_capped(err_path, settings.code_max_output_chars)

    if flooded:
        return failed_all("Your code printed too much output and was stopped.")

    line = next((ln for ln in reversed(stdout.splitlines()) if ln.startswith(marker)), None)
    if line is None:
        if os.name == "posix" and proc.returncode == -signal.SIGXFSZ:
            return failed_all("Your code printed too much output and was stopped.")
        if os.name == "posix" and proc.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
            return failed_all("Your code used too much CPU time or memory and was stopped.")
        return failed_all(f"Your code crashed before finishing.\n{stderr.strip()}".strip())

    payload = json.loads(line[len(marker) :])
    if payload.get("error"):
        return failed_all(payload["error"])

    outcomes = [
        TestOutcome(
            args=t["args"],
            expected=t["expected"],
            hidden=t.get("hidden", False),
            passed=r["passed"],
            output=r["output"],
            error=r["error"],
            stdout=r["stdout"],
        )
        for t, r in zip(tests, payload["results"], strict=True)
    ]
    return RunResult(outcomes=outcomes)
