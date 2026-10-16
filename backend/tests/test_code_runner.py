from app.services.code_runner import run_tests

TESTS = [
    {"args": [2, 3], "expected": 5, "hidden": False},
    {"args": [-1, 1], "expected": 0, "hidden": True},
]


def test_correct_code_passes():
    r = run_tests("def add(a, b):\n    return a + b\n", "add", TESTS)
    assert (r.passed, r.total, r.error) == (2, 2, None)


def test_wrong_answer_reports_output():
    r = run_tests("def add(a, b):\n    return a - b\n", "add", TESTS)
    assert r.passed == 0
    assert r.outcomes[0].output == -1


def test_syntax_error_is_reported():
    r = run_tests("def add(a, b)\n    return a + b\n", "add", TESTS)
    assert r.passed == 0
    assert "SyntaxError" in r.error


def test_missing_function_is_reported():
    r = run_tests("def plus(a, b):\n    return a + b\n", "add", TESTS)
    assert "add" in r.error and "not defined" in r.error


def test_runtime_error_in_one_test_does_not_stop_others():
    code = "def add(a, b):\n    if a < 0:\n        raise ValueError('neg')\n    return a + b\n"
    r = run_tests(code, "add", TESTS)
    assert r.outcomes[0].passed and not r.outcomes[1].passed
    assert "ValueError: neg" in r.outcomes[1].error


def test_infinite_loop_times_out():
    r = run_tests("def add(a, b):\n    while True:\n        pass\n", "add", TESTS)
    assert r.timed_out and r.passed == 0
    assert "Time limit" in r.error


def test_prints_are_captured_not_mixed_with_results():
    code = "print('loading')\ndef add(a, b):\n    print('debug', a)\n    return a + b\n"
    r = run_tests(code, "add", TESTS)
    assert r.passed == 2
    assert r.outcomes[0].stdout.strip() == "debug 2"


def test_tuples_compare_equal_to_lists_and_floats_use_tolerance():
    tests = [{"args": [], "expected": [1, 2], "hidden": False}, {"args": [], "expected": 0.3, "hidden": False}]
    r = run_tests("def f():\n    return (1, 2)\n", "f", tests[:1])
    assert r.passed == 1
    r = run_tests("def f():\n    return 0.1 + 0.2\n", "f", tests[1:])
    assert r.passed == 1


def test_inputs_are_not_shared_between_tests():
    code = "def f(xs):\n    xs.append(1)\n    return len(xs)\n"
    tests = [{"args": [[]], "expected": 1, "hidden": False}, {"args": [[]], "expected": 1, "hidden": False}]
    assert run_tests(code, "f", tests).passed == 2


def test_hidden_tests_reveal_only_pass_fail():
    r = run_tests("def add(a, b):\n    return a + b\n", "add", TESTS).public()
    hidden = r["tests"][1]
    assert hidden == {"hidden": True, "passed": True, "error": None}
