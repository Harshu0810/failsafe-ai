"""
rule_engine.py
Deterministic fix suggestions based on error category and type.
No ML required — purely rule-driven pattern matching.

Each suggestion entry provides:
  • short_fix  : a 1-liner action item
  • code_hint  : a concrete Python snippet illustrating the fix
  • explanation: a paragraph explaining *why* this fix works
"""

from dataclasses import dataclass, field
from analyzer.failure_analyzer import AnalysisResult


# ── Suggestion catalogue ──────────────────────────────────────────────────────

# Keyed by (category, error_type).  Lookup falls back to (category, "*")
# then ("*", error_type) then the generic entry.

_CATALOGUE: dict[tuple[str, str], dict] = {

    # ── Undefined Reference ───────────────────────────────────────────────
    ("Undefined Reference", "NameError"): {
        "short_fix": "Define or import the variable before using it.",
        "code_hint": (
            "# Ensure the variable is defined before the block that uses it\n"
            "my_variable = None  # or load from config / function return value\n"
            "if my_variable is None:\n"
            "    raise ValueError('my_variable must be set before this point.')"
        ),
        "explanation": (
            "NameError is raised when Python encounters an identifier that has not been "
            "assigned in any accessible scope.  Guard against this by always initialising "
            "variables at the top of the function or module, and add assertions or raises "
            "to fail fast when required inputs are absent."
        ),
    },

    # ── Type Mismatch ─────────────────────────────────────────────────────
    ("Type Mismatch", "TypeError"): {
        "short_fix": "Cast operands to a compatible type before performing the operation.",
        "code_hint": (
            "# Option A — explicit cast\n"
            "result = int(str_value) + numeric_value\n\n"
            "# Option B — isinstance guard\n"
            "if not isinstance(value, (int, float)):\n"
            "    raise TypeError(f'Expected numeric, got {type(value).__name__}')"
        ),
        "explanation": (
            "Python does not implicitly convert between types.  "
            "Validate input types at function boundaries using isinstance() or "
            "Pydantic models.  For DataFrames use pd.to_numeric(series, errors='coerce') "
            "to safely coerce and replace unconvertible values with NaN."
        ),
    },

    # ── Missing Resource ──────────────────────────────────────────────────
    ("Missing Resource", "FileNotFoundError"): {
        "short_fix": "Check whether the file exists before opening it.",
        "code_hint": (
            "import os\n\n"
            "file_path = 'data/input.csv'\n"
            "if not os.path.exists(file_path):\n"
            "    raise FileNotFoundError(f'Required file not found: {file_path}')\n"
            "with open(file_path) as f:\n"
            "    data = f.read()"
        ),
        "explanation": (
            "Always validate that expected files exist at start-up rather than "
            "discovering the problem mid-pipeline.  Consider using pathlib.Path for "
            "cross-platform paths, and store file locations in a config object so "
            "they are easy to change without code edits."
        ),
    },

    # ── Bounds Violation ──────────────────────────────────────────────────
    ("Bounds Violation", "IndexError"): {
        "short_fix": "Check the collection length before accessing by index.",
        "code_hint": (
            "items = get_items()\n"
            "if not items:\n"
            "    raise ValueError('items list is empty.')\n"
            "first = items[0]  # safe after length check\n\n"
            "# Or use .get() pattern for safer indexing\n"
            "value = items[idx] if idx < len(items) else default_value"
        ),
        "explanation": (
            "IndexError occurs when code assumes a fixed collection size that "
            "varies at runtime.  Validate lengths before index access, prefer "
            "iteration over index arithmetic, and use enumerate() when you need both "
            "the position and the value."
        ),
    },

    # ── Arithmetic Error ──────────────────────────────────────────────────
    ("Arithmetic Error", "ZeroDivisionError"): {
        "short_fix": "Guard every division with a denominator != 0 check.",
        "code_hint": (
            "denominator = compute_total()\n"
            "if denominator == 0:\n"
            "    ratio = 0.0  # or raise, or return early\n"
            "else:\n"
            "    ratio = numerator / denominator"
        ),
        "explanation": (
            "A zero divisor is often a sign that upstream data is empty or "
            "aggregation produced no records.  Validate that counts are non-zero "
            "before division, or use numpy.where(denom != 0, num / denom, 0) for "
            "vectorised safety."
        ),
    },

    # ── Missing Dependency ────────────────────────────────────────────────
    ("Missing Dependency", "ModuleNotFoundError"): {
        "short_fix": "Install the missing package with pip and pin the version in requirements.txt.",
        "code_hint": (
            "# requirements.txt entry\n"
            "some_package==1.2.3\n\n"
            "# Optional runtime guard\n"
            "try:\n"
            "    import some_package\n"
            "except ModuleNotFoundError:\n"
            "    raise RuntimeError('Run: pip install some_package')"
        ),
        "explanation": (
            "Keep a requirements.txt (or pyproject.toml) in the project root so "
            "any developer can reproduce the environment with `pip install -r requirements.txt`. "
            "In production, build a Docker image that pre-installs all dependencies."
        ),
    },

    # ── Infinite Recursion ────────────────────────────────────────────────
    ("Infinite Recursion", "RecursionError"): {
        "short_fix": "Add a base case to every recursive function.",
        "code_hint": (
            "def factorial(n: int) -> int:\n"
            "    if n < 0:\n"
            "        raise ValueError('n must be >= 0')\n"
            "    if n == 0:        # base case — terminates recursion\n"
            "        return 1\n"
            "    return n * factorial(n - 1)"
        ),
        "explanation": (
            "Every recursive function must have at least one base case that stops "
            "the recursion.  If the depth is large, convert the algorithm to an "
            "iterative form or increase sys.setrecursionlimit() with care."
        ),
    },

    # ── Missing Key / Column ──────────────────────────────────────────────
    ("Missing Key / Column", "KeyError"): {
        "short_fix": "Validate that all expected keys/columns exist before accessing them.",
        "code_hint": (
            "required_cols = {'user_id', 'timestamp', 'value'}\n"
            "missing = required_cols - set(df.columns)\n"
            "if missing:\n"
            "    raise KeyError(f'DataFrame is missing columns: {missing}')\n\n"
            "# For dicts use .get() with a default\n"
            "value = record.get('key', default_value)"
        ),
        "explanation": (
            "KeyError on a DataFrame usually means the upstream data source changed "
            "its schema.  Add a schema validation step (e.g. with pandera or a "
            "simple set-difference check) at ingestion time so failures surface "
            "immediately rather than deep inside the pipeline."
        ),
    },

    # ── Missing Attribute ─────────────────────────────────────────────────
    ("Missing Attribute", "AttributeError"): {
        "short_fix": "Use hasattr() or duck-typing checks before calling the attribute.",
        "code_hint": (
            "if hasattr(obj, 'process'):\n"
            "    obj.process()\n"
            "else:\n"
            "    raise AttributeError(f'{type(obj).__name__} has no method process()')"
        ),
        "explanation": (
            "AttributeError commonly occurs when an object is None (forgot to "
            "initialise), or when a dependency was upgraded and renamed a method.  "
            "Add type hints and runtime isinstance() guards at public API boundaries."
        ),
    },

    # ── Data Corruption ───────────────────────────────────────────────────
    ("Data Corruption", "ValueError"): {
        "short_fix": "Use pd.to_numeric(errors='coerce') to handle corrupted numeric strings.",
        "code_hint": (
            "import pandas as pd\n\n"
            "df['amount'] = pd.to_numeric(df['amount'], errors='coerce')\n"
            "n_bad = df['amount'].isna().sum()\n"
            "if n_bad > 0:\n"
            "    print(f'Warning: {n_bad} rows had non-numeric values in amount.')\n"
            "df = df.dropna(subset=['amount'])  # or fill with a default"
        ),
        "explanation": (
            "Corrupted string columns (e.g. '42abc') are a common data-quality issue "
            "in CSV pipelines.  Coercing with errors='coerce' replaces unparseable "
            "values with NaN, which can then be handled explicitly rather than "
            "crashing the pipeline."
        ),
    },

    # ── Timeout ───────────────────────────────────────────────────────────
    ("Timeout / Infinite Loop", "TimeoutError"): {
        "short_fix": "Refactor loops to guarantee termination, or add an explicit iteration cap.",
        "code_hint": (
            "MAX_ITERATIONS = 10_000\n"
            "iterations = 0\n"
            "while condition:\n"
            "    do_work()\n"
            "    iterations += 1\n"
            "    if iterations >= MAX_ITERATIONS:\n"
            "        raise RuntimeError('Exceeded maximum iterations — possible infinite loop.')"
        ),
        "explanation": (
            "Infinite loops are typically caused by a loop condition that never "
            "becomes False, or blocking I/O without a timeout.  Always add an "
            "upper bound on iterations, and use socket/requests timeouts for "
            "any network calls."
        ),
    },

    # ── Schema Violation ─────────────────────────────────────────────────
    ("Schema Violation", "KeyError"): {
        "short_fix": "Add a schema validation step at data ingestion.",
        "code_hint": (
            "EXPECTED_SCHEMA = {'id': 'int64', 'name': 'object', 'value': 'float64'}\n\n"
            "def validate_schema(df):\n"
            "    for col, dtype in EXPECTED_SCHEMA.items():\n"
            "        if col not in df.columns:\n"
            "            raise KeyError(f'Missing required column: {col}')\n"
            "        if str(df[col].dtype) != dtype:\n"
            "            raise TypeError(f'{col} expected {dtype}, got {df[col].dtype}')\n\n"
            "validate_schema(df)"
        ),
        "explanation": (
            "A schema change in the data source (renamed column, dropped field) is "
            "one of the most common production failures.  Define expected column names "
            "and dtypes explicitly, and validate at the pipeline entry point."
        ),
    },

    # ── Generic fallback ──────────────────────────────────────────────────
    ("Unknown Failure", ""): {
        "short_fix": "Add structured error handling with logging around the failing section.",
        "code_hint": (
            "import logging\n"
            "import traceback\n\n"
            "logger = logging.getLogger(__name__)\n\n"
            "try:\n"
            "    result = risky_operation()\n"
            "except Exception as exc:\n"
            "    logger.error('Unexpected failure: %s', exc, exc_info=True)\n"
            "    raise  # re-raise after logging"
        ),
        "explanation": (
            "Wrap critical code paths in try/except blocks, log the full traceback, "
            "and re-raise or handle gracefully.  Never silently swallow exceptions "
            "without at minimum logging them."
        ),
    },
}


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class Suggestion:
    short_fix: str
    code_hint: str
    explanation: str
    ollama_enhanced: str = ""   # populated later if Ollama is available

    def to_dict(self) -> dict:
        return {
            "short_fix": self.short_fix,
            "code_hint": self.code_hint,
            "explanation": self.explanation,
            "ollama_enhanced": self.ollama_enhanced,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class RuleSuggestionEngine:
    """
    Maps an AnalysisResult to a concrete Suggestion using the rule catalogue.
    """

    def suggest(self, analysis: AnalysisResult) -> Suggestion:
        key = (analysis.category, analysis.error_type)
        entry = (
            _CATALOGUE.get(key)
            or _CATALOGUE.get((analysis.category, ""))
            or _CATALOGUE.get(("Unknown Failure", ""))
        )
        return Suggestion(**entry)

    def suggest_batch(self, analyses: list[AnalysisResult]) -> list[Suggestion]:
        return [self.suggest(a) for a in analyses]
