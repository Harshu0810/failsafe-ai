"""
test_failsafe.py
Pytest tests for the core FailSafe AI modules.
Run with:  pytest tests/test_failsafe.py -v
"""

import os
import sys
import textwrap

import pandas as pd
import pytest

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from injector.code_injector import CodeInjector
from injector.data_injector import DataInjector
from sandbox.executor import Executor
from analyzer.failure_analyzer import FailureAnalyzer
from suggestions.rule_engine import RuleSuggestionEngine


# ── Fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_SCRIPT = textwrap.dedent("""\
    x = 1 + 1
    print(f"Result: {x}")
""")

SAMPLE_DF = pd.DataFrame({
    "id": [1, 2, 3],
    "name": ["Alice", "Bob", "Carol"],
    "score": [90.0, 85.5, 72.0],
})


# ── CodeInjector ──────────────────────────────────────────────────────────────

class TestCodeInjector:

    def test_available_injections_not_empty(self):
        ci = CodeInjector(SIMPLE_SCRIPT)
        assert len(ci.available_injections()) > 0

    def test_unknown_injection_graceful(self):
        ci = CodeInjector(SIMPLE_SCRIPT)
        results = ci.run(["__nonexistent__"])
        assert len(results) == 1
        assert "ERROR" in results[0]["scenario"]

    def test_undefined_variable_injection_modifies_source(self):
        ci = CodeInjector(SIMPLE_SCRIPT)
        results = ci.run(["undefined_variable"])
        assert "__THIS_DOES_NOT_EXIST__" in results[0]["modified_source"]

    def test_original_unchanged_after_injection(self):
        ci = CodeInjector(SIMPLE_SCRIPT)
        ci.run(["key_error", "division_by_zero"])
        assert ci.original == SIMPLE_SCRIPT


# ── DataInjector ──────────────────────────────────────────────────────────────

class TestDataInjector:

    def test_available_injections_not_empty(self):
        di = DataInjector(df=SAMPLE_DF)
        assert len(di.available_injections()) > 0

    def test_missing_values_introduces_nan(self):
        di = DataInjector(df=SAMPLE_DF)
        results = di.run(["missing_values"])
        modified = results[0]["modified_df"]
        assert modified.isna().any().any()

    def test_empty_dataset_produces_zero_rows(self):
        di = DataInjector(df=SAMPLE_DF)
        results = di.run(["empty_dataset"])
        modified = results[0]["modified_df"]
        assert len(modified) == 0
        assert list(modified.columns) == list(SAMPLE_DF.columns)

    def test_duplicate_rows_doubles_row_count(self):
        di = DataInjector(df=SAMPLE_DF)
        results = di.run(["duplicate_rows"])
        modified = results[0]["modified_df"]
        assert len(modified) == len(SAMPLE_DF) * 2

    def test_original_df_is_not_mutated(self):
        di = DataInjector(df=SAMPLE_DF)
        di.run(["missing_values", "null_column", "empty_dataset"])
        pd.testing.assert_frame_equal(di.original, SAMPLE_DF)

    def test_wrong_dtypes_corrupts_numeric_column(self):
        di = DataInjector(df=SAMPLE_DF)
        results = di.run(["wrong_dtypes"])
        modified = results[0]["modified_df"]
        # At least one column should now be object dtype where it wasn't before
        before_dtypes = {c: str(SAMPLE_DF[c].dtype) for c in SAMPLE_DF.columns}
        after_dtypes = {c: str(modified[c].dtype) for c in modified.columns}
        # If the column was numeric, it's now object
        changes = [c for c in SAMPLE_DF.columns if before_dtypes[c] != after_dtypes.get(c, "")]
        assert len(changes) >= 1


# ── Executor (sandbox) ────────────────────────────────────────────────────────

class TestExecutor:

    def test_clean_script_exits_zero(self):
        ex = Executor(timeout_seconds=5)
        result = ex.run('print("hello")', "clean_run")
        assert result.exit_code == 0
        assert result.stdout == "hello"
        assert result.success is True

    def test_name_error_captured(self):
        ex = Executor(timeout_seconds=5)
        result = ex.run("print(undefined_var)", "name_error_test")
        assert result.exit_code != 0
        assert "NameError" in result.error_type

    def test_timeout_triggers(self):
        ex = Executor(timeout_seconds=2)
        result = ex.run(
            "import time\nwhile True:\n    time.sleep(0.1)",
            "infinite_loop_test",
        )
        assert result.timed_out is True

    def test_division_by_zero_captured(self):
        ex = Executor(timeout_seconds=5)
        result = ex.run("x = 1 / 0", "div_by_zero_test")
        assert "ZeroDivisionError" in result.error_type


class TestExecutorProject:
    """Tests for the multi-file run_project() sandbox method."""

    def test_single_file_project(self):
        ex = Executor(timeout_seconds=5)
        r = ex.run_project({"main.py": b'print("hello project")'}, "main.py")
        assert r.exit_code == 0
        assert r.stdout == "hello project"

    def test_multi_file_helper_import(self):
        ex = Executor(timeout_seconds=5)
        files = {
            "helper.py": b'def greet():\n    return "hello from helper"\n',
            "main.py": b'from helper import greet\nprint(greet())\n',
        }
        r = ex.run_project(files, "main.py")
        assert r.exit_code == 0
        assert r.stdout == "hello from helper"

    def test_missing_module_surfaced_without_requirements(self):
        ex = Executor(timeout_seconds=5)
        r = ex.run_project(
            {"main.py": b"import nonexistent_pkg_xyz_failsafe\nprint('ok')"},
            "main.py",
        )
        assert r.exit_code != 0
        assert "ModuleNotFoundError" in r.error_type or r.exit_code != 0

    def test_requirements_txt_installed_before_run(self):
        """requests is already in the venv — verifies pip path is exercised."""
        ex = Executor(timeout_seconds=30)
        files = {
            "requirements.txt": b"requests>=2.0\n",
            "main.py": b"import requests\nprint('requests OK')\n",
        }
        r = ex.run_project(files, "main.py")
        assert r.exit_code == 0
        assert "requests OK" in r.stdout



# ── FailureAnalyzer ───────────────────────────────────────────────────────────

class TestFailureAnalyzer:

    def _make_result(self, error_type, error_msg="", traceback=""):
        from sandbox.executor import ExecutionResult
        r = ExecutionResult()
        r.error_type = error_type
        r.error_message = error_msg
        r.traceback = traceback
        return r

    def test_name_error_category(self):
        fa = FailureAnalyzer()
        ar = fa.analyze(self._make_result("NameError"))
        assert ar.category == "Undefined Reference"
        assert ar.severity == "high"

    def test_zero_division_is_critical(self):
        fa = FailureAnalyzer()
        ar = fa.analyze(self._make_result("ZeroDivisionError"))
        assert ar.severity == "critical"

    def test_timeout_result_is_critical(self):
        from sandbox.executor import ExecutionResult
        r = ExecutionResult()
        r.timed_out = True
        r.error_type = "TimeoutError"
        fa = FailureAnalyzer()
        ar = fa.analyze(r)
        assert ar.severity == "critical"
        assert "Timeout" in ar.category

    def test_unknown_error_has_fallback(self):
        fa = FailureAnalyzer()
        ar = fa.analyze(self._make_result("WeirdObscureError"))
        assert ar.root_cause  # non-empty string
        assert ar.category == "Unknown Failure"


# ── RuleSuggestionEngine ──────────────────────────────────────────────────────

class TestRuleSuggestionEngine:

    def _make_analysis(self, category, error_type):
        from analyzer.failure_analyzer import AnalysisResult
        ar = AnalysisResult()
        ar.category = category
        ar.error_type = error_type
        return ar

    def test_suggestion_has_required_fields(self):
        engine = RuleSuggestionEngine()
        ar = self._make_analysis("Type Mismatch", "TypeError")
        sug = engine.suggest(ar)
        assert sug.short_fix
        assert sug.code_hint
        assert sug.explanation

    def test_unknown_category_returns_generic_suggestion(self):
        engine = RuleSuggestionEngine()
        ar = self._make_analysis("Completely Unknown", "WeirdError")
        sug = engine.suggest(ar)
        assert sug.short_fix  # should not raise

    def test_batch_same_length(self):
        engine = RuleSuggestionEngine()
        analyses = [
            self._make_analysis("Type Mismatch", "TypeError"),
            self._make_analysis("Missing Resource", "FileNotFoundError"),
            self._make_analysis("Arithmetic Error", "ZeroDivisionError"),
        ]
        suggestions = engine.suggest_batch(analyses)
        assert len(suggestions) == len(analyses)
