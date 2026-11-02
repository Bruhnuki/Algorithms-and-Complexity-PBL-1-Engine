"""Dependency-free test runner (use `pytest` if you have it)."""
import inspect, sys
import tests.test_engines as t
failed = 0
for name, fn in inspect.getmembers(t, inspect.isfunction):
    if name.startswith("test_"):
        try:
            fn(); print("PASS", name)
        except Exception as e:
            failed += 1; print("FAIL", name, "->", repr(e)[:300])
sys.exit(1 if failed else 0)
