"""
data_injector.py
Injects controlled failures into pandas DataFrames / CSV files.
Each injection method returns a (modified_df, scenario_description) tuple.
"""

import random
import numpy as np
import pandas as pd
from typing import Callable

# ── Registry of all available injection strategies ──────────────────────────
# Key   : string identifier shown in the UI
# Value : callable that accepts a DataFrame and returns (df, description)

INJECTION_REGISTRY: dict[str, Callable[[pd.DataFrame], tuple[pd.DataFrame, str]]] = {}


def register(name: str):
    """Decorator that registers an injection function under *name*."""
    def decorator(fn):
        INJECTION_REGISTRY[name] = fn
        return fn
    return decorator


# ── Helper ───────────────────────────────────────────────────────────────────

def _random_column(df: pd.DataFrame) -> str:
    """Pick a random column name from *df*."""
    return random.choice(df.columns.tolist())


# ── Injection strategies ─────────────────────────────────────────────────────

@register("missing_values")
def inject_missing_values(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Randomly scatter NaN values across ~20 % of cells."""
    df = df.copy()
    n_rows, n_cols = df.shape
    mask = np.random.random((n_rows, n_cols)) < 0.20
    df[mask] = np.nan
    count = int(mask.sum())
    return df, f"Injected {count} missing values (NaN) spread randomly across the dataset."


@register("null_column")
def inject_null_column(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Replace an entire column with NaN."""
    df = df.copy()
    col = _random_column(df)
    df[col] = np.nan
    return df, f"Column '{col}' was entirely replaced with NaN (simulates a dropped or corrupted column)."


@register("wrong_dtypes")
def inject_wrong_dtypes(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Convert a numeric column to mixed-type strings (e.g., '42abc')."""
    df = df.copy()
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        # Fall back to corrupting a random column
        col = _random_column(df)
        df[col] = df[col].astype(str) + "_corrupt"
        return df, f"Column '{col}' corrupted to strings (no numeric columns found)."
    col = random.choice(numeric_cols)
    df[col] = df[col].astype(str) + "abc"  # forces object dtype
    return df, (
        f"Column '{col}' converted to corrupted strings (e.g., '42abc'). "
        "Downstream numeric operations will raise TypeError / ValueError."
    )


@register("empty_dataset")
def inject_empty_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Return a DataFrame with zero rows but intact schema."""
    empty = df.iloc[0:0].copy()
    return empty, "Dataset truncated to 0 rows while preserving column headers."


@register("duplicate_rows")
def inject_duplicate_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Duplicate every row (100 % duplication rate)."""
    df_dup = pd.concat([df, df], ignore_index=True)
    return df_dup, (
        f"All {len(df)} rows duplicated → {len(df_dup)} total rows. "
        "Aggregations and unique-value checks will be skewed."
    )


@register("wrong_column_name")
def inject_wrong_column_name(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Rename a random column to a garbled name."""
    df = df.copy()
    col = _random_column(df)
    bad_name = col + "_BROKEN"
    df.rename(columns={col: bad_name}, inplace=True)
    return df, (
        f"Column '{col}' renamed to '{bad_name}'. "
        "Any code referencing the original name will raise a KeyError."
    )


@register("extra_whitespace")
def inject_extra_whitespace(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Pad string columns with leading/trailing spaces."""
    df = df.copy()
    str_cols = df.select_dtypes(include=["object"]).columns.tolist()
    if not str_cols:
        return df, "No string columns found; whitespace injection skipped."
    for col in str_cols:
        df[col] = "  " + df[col].astype(str) + "  "
    return df, (
        f"Added leading/trailing whitespace to {len(str_cols)} string columns: "
        f"{str_cols}. String comparisons and joins will silently fail."
    )


# ── Public API ────────────────────────────────────────────────────────────────

class DataInjector:
    """
    High-level API for injecting failures into a CSV / DataFrame.

    Usage::

        injector = DataInjector("path/to/file.csv")
        results  = injector.run(["missing_values", "wrong_dtypes"])
        for r in results:
            print(r["scenario"], r["modified_df"].shape)
    """

    def __init__(self, csv_path: str | None = None, df: pd.DataFrame | None = None):
        if df is not None:
            self._original = df.copy()
        elif csv_path:
            self._original = pd.read_csv(csv_path)
        else:
            raise ValueError("Provide either csv_path or a DataFrame.")

    @property
    def original(self) -> pd.DataFrame:
        return self._original.copy()

    @staticmethod
    def available_injections() -> list[str]:
        return list(INJECTION_REGISTRY.keys())

    def run(self, injection_names: list[str]) -> list[dict]:
        """
        Apply each requested injection independently on the original data.

        Returns a list of dicts::

            {
                "injection"  : str,           # name of the injection
                "scenario"   : str,           # human-readable description
                "modified_df": pd.DataFrame,  # the mutated dataset
                "original_df": pd.DataFrame,  # untouched reference copy
            }
        """
        results = []
        for name in injection_names:
            fn = INJECTION_REGISTRY.get(name)
            if fn is None:
                results.append({
                    "injection": name,
                    "scenario": f"[ERROR] Unknown injection '{name}'.",
                    "modified_df": self._original.copy(),
                    "original_df": self._original.copy(),
                })
                continue
            modified_df, scenario = fn(self._original.copy())
            results.append({
                "injection": name,
                "scenario": scenario,
                "modified_df": modified_df,
                "original_df": self._original.copy(),
            })
        return results
