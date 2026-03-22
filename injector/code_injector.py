"""
code_injector.py
Transforms a Python source string by injecting realistic fault patterns.
Each injection returns (modified_source, scenario_description).
"""

import ast
import random
import re
import textwrap
from typing import Callable

# ── Registry ─────────────────────────────────────────────────────────────────

INJECTION_REGISTRY: dict[str, Callable[[str], tuple[str, str]]] = {}


def register(name: str):
    def decorator(fn):
        INJECTION_REGISTRY[name] = fn
        return fn
    return decorator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _insert_after_imports(source: str, snippet: str) -> str:
    """Insert *snippet* after the last top-level import statement."""
    lines = source.splitlines()
    last_import = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import = i
    lines.insert(last_import + 1, snippet)
    return "\n".join(lines)


def _prepend(source: str, snippet: str) -> str:
    return snippet + "\n" + source


def _append(source: str, snippet: str) -> str:
    return source + "\n" + snippet


# ── Injections ────────────────────────────────────────────────────────────────

@register("undefined_variable")
def inject_undefined_variable(source: str) -> tuple[str, str]:
    """Reference a variable that doesn't exist."""
    snippet = "\n# [INJECTED] undefined variable\n_undefined_var = __THIS_DOES_NOT_EXIST__\n"
    return _insert_after_imports(source, snippet), (
        "Appended a reference to an undefined variable '__THIS_DOES_NOT_EXIST__'. "
        "Expected: NameError."
    )


@register("wrong_type_operation")
def inject_wrong_type_operation(source: str) -> tuple[str, str]:
    """Perform an arithmetic operation on incompatible types."""
    snippet = (
        '\n# [INJECTED] type mismatch\n'
        '_type_trap = "hello" + 42  # str + int → TypeError\n'
    )
    return _insert_after_imports(source, snippet), (
        "Appended 'string + integer' operation. Expected: TypeError."
    )


@register("file_not_found")
def inject_file_not_found(source: str) -> tuple[str, str]:
    """Attempt to open a guaranteed-missing file."""
    snippet = (
        '\n# [INJECTED] missing file\n'
        'with open("/tmp/__failsafe_nonexistent_file_xyz__.txt", "r") as _f:\n'
        '    _data = _f.read()\n'
    )
    return _insert_after_imports(source, snippet), (
        "Appended open() call for a non-existent file path. "
        "Expected: FileNotFoundError."
    )


@register("index_out_of_range")
def inject_index_error(source: str) -> tuple[str, str]:
    """Access a list index that is out of range."""
    snippet = (
        '\n# [INJECTED] index out of range\n'
        '_lst = [1, 2, 3]\n'
        '_val = _lst[999]  # IndexError\n'
    )
    return _insert_after_imports(source, snippet), (
        "Appended an out-of-range list access (_lst[999]). Expected: IndexError."
    )


@register("division_by_zero")
def inject_division_by_zero(source: str) -> tuple[str, str]:
    """Force a ZeroDivisionError."""
    snippet = (
        '\n# [INJECTED] division by zero\n'
        '_div = 1 / 0\n'
    )
    return _insert_after_imports(source, snippet), (
        "Appended '1 / 0'. Expected: ZeroDivisionError."
    )


@register("import_error")
def inject_import_error(source: str) -> tuple[str, str]:
    """Import a module that does not exist."""
    snippet = (
        '\n# [INJECTED] bad import\n'
        'import __failsafe_nonexistent_module_xyz__\n'
    )
    return _insert_after_imports(source, snippet), (
        "Inserted import of a non-existent module. Expected: ModuleNotFoundError."
    )


@register("infinite_loop")
def inject_slow_loop(source: str) -> tuple[str, str]:
    """
    Inject a loop that runs for 10 seconds — the sandbox timeout should
    catch it rather than it genuinely hanging forever.
    """
    snippet = (
        '\n# [INJECTED] simulated timeout-triggering loop\n'
        'import time as _time\n'
        '_start = _time.time()\n'
        'while True:\n'
        '    if _time.time() - _start > 10:\n'
        '        break\n'
    )
    return _insert_after_imports(source, snippet), (
        "Injected a loop that spins for 10 s, simulating a timeout scenario. "
        "The sandbox execution limit will trigger before it exits."
    )


@register("recursion_error")
def inject_recursion_error(source: str) -> tuple[str, str]:
    """Define and call an infinitely-recursive function."""
    snippet = (
        '\n# [INJECTED] infinite recursion\n'
        'def _recurse(n): return _recurse(n + 1)\n'
        '_recurse(0)\n'
    )
    return _insert_after_imports(source, snippet), (
        "Appended infinite recursion call. Expected: RecursionError."
    )


@register("key_error")
def inject_key_error(source: str) -> tuple[str, str]:
    """Access a missing dictionary key."""
    snippet = (
        '\n# [INJECTED] missing dict key\n'
        '_d = {"a": 1}\n'
        '_val = _d["__missing_key__"]\n'
    )
    return _insert_after_imports(source, snippet), (
        "Appended dictionary access with a non-existent key. Expected: KeyError."
    )


@register("attribute_error")
def inject_attribute_error(source: str) -> tuple[str, str]:
    """Call a method that doesn't exist on an object."""
    snippet = (
        '\n# [INJECTED] bad attribute\n'
        '_obj = object()\n'
        '_obj.nonexistent_method()  # AttributeError\n'
    )
    return _insert_after_imports(source, snippet), (
        "Called a non-existent method on a plain object. Expected: AttributeError."
    )


# ── Public API ────────────────────────────────────────────────────────────────

class CodeInjector:
    """
    High-level API for injecting failures into Python source code.

    Usage::

        ci = CodeInjector(source_code)
        results = ci.run(["undefined_variable", "file_not_found"])
        for r in results:
            print(r["injection"], r["scenario"])
    """

    def __init__(self, source: str):
        self._original = source

    @staticmethod
    def available_injections() -> list[str]:
        return list(INJECTION_REGISTRY.keys())

    @property
    def original(self) -> str:
        return self._original

    def run(self, injection_names: list[str]) -> list[dict]:
        """
        Apply each injection *independently* to the original source.

        Returns a list of dicts::

            {
                "injection"      : str,  # injection name
                "scenario"       : str,  # human description
                "modified_source": str,  # mutated Python code
            }
        """
        results = []
        for name in injection_names:
            fn = INJECTION_REGISTRY.get(name)
            if fn is None:
                results.append({
                    "injection": name,
                    "scenario": f"[ERROR] Unknown injection '{name}'.",
                    "modified_source": self._original,
                })
                continue
            modified, scenario = fn(self._original)
            results.append({
                "injection": name,
                "scenario": scenario,
                "modified_source": modified,
            })
        return results
