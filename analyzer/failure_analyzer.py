"""
failure_analyzer.py
Maps captured errors → human-readable root-cause explanations using
a rule-based pattern engine.  No external ML is required.

Design decision: every rule is a plain Python dict so the mapping table
is easy to extend, audit, and test.
"""

import re
from dataclasses import dataclass, field

from sandbox.executor import ExecutionResult


# ── Rule table ────────────────────────────────────────────────────────────────
# Each rule has:
#   error_type   : exact Python exception class name (or "" to match any)
#   pattern      : optional regex applied to error_message / traceback
#   root_cause   : one-line explanation
#   category     : broad failure category for grouping in the report
#   severity     : "critical" | "high" | "medium" | "low"

_RULES: list[dict] = [
    # ── NameError ──────────────────────────────────────────────────────────
    {
        "error_type": "NameError",
        "pattern": None,
        "root_cause": "A variable or function is used before it is defined or imported.",
        "category": "Undefined Reference",
        "severity": "high",
    },
    # ── TypeError ──────────────────────────────────────────────────────────
    {
        "error_type": "TypeError",
        "pattern": r"unsupported operand type",
        "root_cause": "An operation was applied to incompatible data types (e.g. str + int).",
        "category": "Type Mismatch",
        "severity": "high",
    },
    {
        "error_type": "TypeError",
        "pattern": None,
        "root_cause": "A function received an argument of the wrong type.",
        "category": "Type Mismatch",
        "severity": "medium",
    },
    # ── FileNotFoundError ──────────────────────────────────────────────────
    {
        "error_type": "FileNotFoundError",
        "pattern": None,
        "root_cause": "The script tried to open a file that does not exist.",
        "category": "Missing Resource",
        "severity": "high",
    },
    # ── IndexError ─────────────────────────────────────────────────────────
    {
        "error_type": "IndexError",
        "pattern": r"list index out of range",
        "root_cause": "A list or array was accessed with an index beyond its length.",
        "category": "Bounds Violation",
        "severity": "high",
    },
    {
        "error_type": "IndexError",
        "pattern": None,
        "root_cause": "Sequence index is out of bounds.",
        "category": "Bounds Violation",
        "severity": "high",
    },
    # ── ZeroDivisionError ──────────────────────────────────────────────────
    {
        "error_type": "ZeroDivisionError",
        "pattern": None,
        "root_cause": "A division or modulo operation has zero as its divisor.",
        "category": "Arithmetic Error",
        "severity": "critical",
    },
    # ── ModuleNotFoundError ────────────────────────────────────────────────
    {
        "error_type": "ModuleNotFoundError",
        "pattern": None,
        "root_cause": "An imported module is not installed or the import path is wrong.",
        "category": "Missing Dependency",
        "severity": "critical",
    },
    # ── RecursionError ─────────────────────────────────────────────────────
    {
        "error_type": "RecursionError",
        "pattern": None,
        "root_cause": "A function calls itself indefinitely with no base case.",
        "category": "Infinite Recursion",
        "severity": "critical",
    },
    # ── KeyError ───────────────────────────────────────────────────────────
    {
        "error_type": "KeyError",
        "pattern": None,
        "root_cause": "A dictionary (or DataFrame) was accessed with a key that does not exist.",
        "category": "Missing Key / Column",
        "severity": "high",
    },
    # ── AttributeError ─────────────────────────────────────────────────────
    {
        "error_type": "AttributeError",
        "pattern": None,
        "root_cause": "An attribute or method was accessed on an object that does not have it.",
        "category": "Missing Attribute",
        "severity": "medium",
    },
    # ── ValueError ─────────────────────────────────────────────────────────
    {
        "error_type": "ValueError",
        "pattern": r"could not convert",
        "root_cause": "A string value could not be converted to a numeric type — likely due to corrupted data.",
        "category": "Data Corruption",
        "severity": "high",
    },
    {
        "error_type": "ValueError",
        "pattern": None,
        "root_cause": "A function received an argument with an inappropriate value.",
        "category": "Invalid Value",
        "severity": "medium",
    },
    # ── TimeoutError (custom sandbox signal) ──────────────────────────────
    {
        "error_type": "TimeoutError",
        "pattern": None,
        "root_cause": "Execution exceeded the configured sandbox time limit — likely an infinite loop or blocking I/O.",
        "category": "Timeout / Infinite Loop",
        "severity": "critical",
    },
    # ── Pandas-specific ────────────────────────────────────────────────────
    {
        "error_type": "KeyError",
        "pattern": r"not in index",
        "root_cause": "A required DataFrame column is missing — the dataset schema may have changed.",
        "category": "Schema Violation",
        "severity": "high",
    },
    # ── Generic fallback ───────────────────────────────────────────────────
    {
        "error_type": "",
        "pattern": None,
        "root_cause": "An unclassified error occurred during execution.",
        "category": "Unknown Failure",
        "severity": "medium",
    },
]


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    """Output of FailureAnalyzer.analyze()."""

    injection_name: str = ""
    scenario: str = ""

    error_type: str = ""
    error_message: str = ""
    traceback: str = ""
    timed_out: bool = False
    execution_time_ms: float = 0.0

    root_cause: str = ""
    category: str = ""
    severity: str = ""
    matched_rule: dict = field(default_factory=dict)

    stdout: str = ""

    @property
    def passed(self) -> bool:
        """True when no error was detected (unexpected pass-through)."""
        return not self.error_type and not self.timed_out

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["matched_rule"] = self.matched_rule
        d["passed"] = self.passed
        return d


# ── Analyzer ──────────────────────────────────────────────────────────────────

class FailureAnalyzer:
    """
    Consumes an ExecutionResult and returns an AnalysisResult with
    enriched root-cause and severity information.
    """

    def analyze(self, exec_result: ExecutionResult) -> AnalysisResult:
        ar = AnalysisResult(
            injection_name=exec_result.injection_name,
            scenario=exec_result.scenario,
            error_type=exec_result.error_type,
            error_message=exec_result.error_message,
            traceback=exec_result.traceback,
            timed_out=exec_result.timed_out,
            execution_time_ms=exec_result.execution_time_ms,
            stdout=exec_result.stdout,
        )

        rule = self._match_rule(exec_result)
        ar.root_cause = rule["root_cause"]
        ar.category = rule["category"]
        ar.severity = rule["severity"]
        ar.matched_rule = rule

        return ar

    def analyze_batch(self, exec_results: list[ExecutionResult]) -> list[AnalysisResult]:
        return [self.analyze(r) for r in exec_results]

    # ── Matching logic ────────────────────────────────────────────────────

    def _match_rule(self, result: ExecutionResult) -> dict:
        """
        Walk the rule table and return the first matching rule.
        Matching priority:
          1. error_type matches AND regex pattern matches message/traceback
          2. error_type matches with no pattern constraint
          3. Generic fallback (last rule, error_type == "")
        """
        # Combine message and traceback for pattern matching
        search_text = f"{result.error_message}\n{result.traceback}".lower()

        # Phase 1 — exact type + pattern
        for rule in _RULES:
            if rule["error_type"] and rule["pattern"]:
                if result.error_type == rule["error_type"]:
                    if re.search(rule["pattern"], search_text, re.IGNORECASE):
                        return rule

        # Phase 2 — exact type, no pattern
        for rule in _RULES:
            if rule["error_type"] and not rule["pattern"]:
                if result.error_type == rule["error_type"]:
                    return rule

        # Phase 3 — timeout special case
        if result.timed_out:
            return {
                "error_type": "TimeoutError",
                "pattern": None,
                "root_cause": "Execution exceeded the sandbox time limit — likely an infinite loop.",
                "category": "Timeout / Infinite Loop",
                "severity": "critical",
            }

        # Fallback
        return _RULES[-1]
