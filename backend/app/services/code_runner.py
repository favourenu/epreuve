"""Runs candidate Python code against test cases in a separate process.

This isolates crashes, infinite loops and stray output from the API process, and
enforces a wall-clock time limit. It is NOT a security sandbox: it is meant for
running your own practice code on your own machine.
"""

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings

RESULT_MARKER = "__ASSESSMENT_RESULT__"

_HARNESS = r'''
import contextlib, copy, io, json, linecache, math, sys, traceback

MARKER = sys.argv[2]
spec = json.load(open(sys.argv[1], encoding="utf-8"))
MAX_OUT = spec["max_output"]


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


def emit(payload):
    sys.__stdout__.write(MARKER + json.dumps(payload) + "\n")


# Lets tracebacks show the candidate's source lines for the virtual solution.py file.
linecache.cache["solution.py"] = (len(spec["code"]), None, spec["code"].splitlines(True), "solution.py")
namespace = {"__name__": "solution"}
setup_out = io.StringIO()
try:
    with contextlib.redirect_stdout(setup_out):
        exec(compile(spec["code"], "solution.py", "exec"), namespace)
except BaseException as exc:
    emit({"error": describe(exc)})
    sys.exit(0)

fn = namespace.get(spec["function_name"])
if not callable(fn):
    emit({"error": f"Function '{spec['function_name']}' is not defined. Keep the function name from the starter code."})
    sys.exit(0)

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
    entry["stdout"] = out.getvalue()[:MAX_OUT]
    results.append(entry)

emit({"error": None, "results": results})
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


def run_tests(code: str, function_name: str, tests: list[dict[str, Any]]) -> RunResult:
    """Run `code` and call `function_name` with each test's args.

    `tests` items: {"args": [...], "expected": ..., "hidden": bool}.
    """
    settings = get_settings()

    def failed_all(error: str, timed_out: bool = False) -> RunResult:
        return RunResult(
            outcomes=[TestOutcome(t["args"], t["expected"], t.get("hidden", False), False) for t in tests],
            error=error,
            timed_out=timed_out,
        )

    spec = {
        "code": code,
        "function_name": function_name,
        "tests": [{"args": t["args"], "expected": t["expected"]} for t in tests],
        "max_output": 2000,
    }
    with tempfile.TemporaryDirectory(prefix="assess-run-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "harness.py").write_text(_HARNESS, encoding="utf-8")
        (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-X", "utf8", "harness.py", "spec.json", RESULT_MARKER],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.code_run_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return failed_all(
                f"Time limit exceeded ({settings.code_run_timeout_seconds:g}s). "
                "Check for infinite loops or an inefficient algorithm.",
                timed_out=True,
            )

    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith(RESULT_MARKER)), None)
    if line is None:
        stderr = proc.stderr.strip()[-settings.code_max_output_chars :]
        return failed_all(f"Your code crashed before finishing.\n{stderr}".strip())

    payload = json.loads(line[len(RESULT_MARKER) :])
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
