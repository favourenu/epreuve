"""Submitted code must not be able to reach secrets, files, the network or other processes."""
import os
import sys

import pytest

from app.services.code_runner import run_tests

ONE_TEST = [{"args": [], "expected": "safe", "hidden": False}]


def attempt(body: str) -> str:
    """Run `body` inside f() and return what the user would see: the error or the output."""
    code = "def f():\n" + "\n".join("    " + line for line in body.strip().splitlines()) + "\n"
    r = run_tests(code, "f", ONE_TEST)
    o = r.outcomes[0]
    return r.error or o.error or repr(o.output)


@pytest.fixture(autouse=True)
def secret_in_server_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "server-secret-should-never-leak")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-never-leak")


def test_server_environment_variables_are_not_visible():
    out = attempt("import os\nreturn dict(os.environ)")
    assert "should-never-leak" not in out
    assert "SECRET_KEY" not in out and "OPENROUTER" not in out


@pytest.mark.parametrize(
    "body, blocked",
    [
        ("return open('../backend/.env').read()", "Opening files"),
        ("return open(__import__('os').path.expanduser('~/.ssh/id_rsa')).read()", "Opening files"),
        ("return open('spec.json').read()", "Opening files"),
        ("open('pwned.txt', 'w').write('x')\nreturn 'safe'", "Writing files"),
        ("import os\nreturn os.listdir('.')", "Listing directories"),
        ("import os\nos.remove('harness.py')\nreturn 'safe'", "Deleting files"),
        ("import os\nreturn os.system('echo hi')", "Running shell commands"),
        # Blocked at import on Windows (msvcrt), at Popen on Linux: either way it's refused.
        ("import subprocess\nreturn subprocess.run(['echo', 'hi'])", "disabled in the code runner"),
        ("import socket\nreturn socket.create_connection(('example.com', 80))", "Network access"),
        ("import urllib.request\nreturn urllib.request.urlopen('http://example.com').read()", "Network access"),
        ("import ctypes\nreturn 'safe'", "Importing 'ctypes'"),
        ("import os\nos.putenv('X', '1')\nreturn 'safe'", "Changing the environment"),
    ],
)
def test_dangerous_actions_are_blocked(body, blocked):
    out = attempt(body)
    # Some libraries wrap the PermissionError (urllib raises URLError), so check the message.
    assert "disabled in the code runner" in out and blocked in out, out


@pytest.mark.skipif(os.name != "posix", reason="fork only exists on Linux/macOS")
def test_fork_is_blocked():
    out = attempt("import os\nos.fork()\nreturn 'safe'")
    assert "Starting processes" in out


@pytest.mark.skipif(sys.platform != "linux", reason="memory limits are enforced on Linux (the deployment target)")
def test_memory_bomb_is_stopped():
    r = run_tests("def f():\n    x = bytearray(2 * 1024**3)\n    return 'safe'\n", "f", ONE_TEST)
    assert r.passed == 0
    assert "MemoryError" in (r.error or r.outcomes[0].error or "")


@pytest.mark.skipif(sys.platform != "linux", reason="output limits are enforced on Linux (the deployment target)")
def test_output_flood_is_stopped():
    r = run_tests("import sys\ndef f():\n    while True:\n        sys.__stdout__.write('x' * 65536)\n", "f", ONE_TEST)
    assert r.passed == 0
    assert r.error == "Your code printed too much output and was stopped."


def test_stdlib_submodules_can_still_be_imported():
    out = attempt(
        "import xml.etree.ElementTree as ET\nimport email.utils\nimport concurrent.futures\n"
        "return ET.fromstring('<a>safe</a>').text"
    )
    assert out == "'safe'", out


def test_normal_solutions_still_work():
    code = (
        "import heapq, math, re, itertools, functools, json, string, datetime, bisect, statistics\n"
        "from collections import Counter, defaultdict, deque, namedtuple, OrderedDict\n"
        "from dataclasses import dataclass\n"
        "from typing import List\n"
        "Point = namedtuple('Point', 'x y')\n"
        "def f():\n"
        "    h = [3, 1, 2]; heapq.heapify(h)\n"
        "    assert heapq.heappop(h) == 1 and math.isqrt(16) == 4 and Counter('aab')['a'] == 2\n"
        "    assert Point(1, 2).x == 1 and re.findall(r'\\d', 'a1b2') == ['1', '2']\n"
        "    print('debug output is fine')\n"
        "    return 'safe'\n"
    )
    r = run_tests(code, "f", ONE_TEST)
    assert r.passed == 1, r.error or r.outcomes[0].error


def test_concurrent_runs_are_limited(monkeypatch):
    import threading
    import time

    from app.services import code_runner

    monkeypatch.setattr(code_runner, "_run_slots", lambda: sem)
    sem = threading.BoundedSemaphore(1)
    sem.acquire()  # simulate a run already in progress
    monkeypatch.setattr(code_runner.get_settings(), "code_queue_wait_seconds", 0.2)
    start = time.monotonic()
    r = run_tests("def f():\n    return 'safe'\n", "f", ONE_TEST)
    assert "busy" in r.error and time.monotonic() - start < 2
    sem.release()
    assert run_tests("def f():\n    return 'safe'\n", "f", ONE_TEST).passed == 1
