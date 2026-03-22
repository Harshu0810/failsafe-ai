"""
sample_script.py
A simple data processing script.  FailSafe AI will inject failures into
a copy of this file and observe the resulting errors.
"""

import csv
import os
import statistics


def load_data(path: str) -> list[dict]:
    """Load a CSV file and return a list of row dicts."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute_avg_salary(records: list[dict]) -> float:
    """Return the mean salary across all records."""
    salaries = [float(r["salary"]) for r in records]
    return statistics.mean(salaries)


def filter_department(records: list[dict], dept: str) -> list[dict]:
    """Return records matching a given department."""
    return [r for r in records if r["department"] == dept]


def summarise(records: list[dict]) -> None:
    departments = set(r["department"] for r in records)
    print(f"Total employees : {len(records)}")
    print(f"Departments     : {', '.join(sorted(departments))}")
    print(f"Average salary  : ${compute_avg_salary(records):,.2f}")

    for dept in sorted(departments):
        dept_records = filter_department(records, dept)
        avg = compute_avg_salary(dept_records)
        print(f"  {dept:15s}: {len(dept_records)} employees, avg salary ${avg:,.2f}")


if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "data", "sample_data.csv")
    records = load_data(data_path)
    summarise(records)
    print("\nScript completed successfully.")
