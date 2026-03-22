# ⚡ FailSafe AI — System Failure Simulator & Debug Assistant

> Inject failures. Observe behaviour. Diagnose root causes. Suggest fixes.
> Fully local · CPU-only · No paid APIs · No cloud dependency.

---

## What it does

FailSafe AI is a portfolio-grade engineering tool that deliberately injects
realistic failure scenarios into your Python scripts or CSV datasets, executes
them in a sandboxed subprocess, captures every error, maps it to a root cause,
and suggests concrete code fixes — optionally enhanced by a local Ollama LLM.

```
User Input → Failure Injection → Execution Sandbox → Error Capture
          → Failure Analysis  → Fix Suggestions   → Report Generator → Streamlit UI
```

---

## System requirements

| Component | Minimum |
|-----------|---------|
| CPU | Intel 4th gen or newer |
| RAM | 4 GB (8 GB recommended for Ollama) |
| Disk | 500 MB (+ ~4 GB per Ollama model) |
| Python | 3.10 + |
| GPU | Not required |

Tested on Python 3.10 / 3.11 / 3.12.

---

## Quick start

### 1. Clone / download the project

```bash
git clone https://github.com/<your-github-handle>/failsafe-ai.git
cd failsafe-ai
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate.bat       # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Streamlit app

```bash
streamlit run app.py
```

The UI opens at **http://localhost:8501** in your browser.

---

## Multi-file project upload

You can upload a full Python project instead of a single script:

1. Switch to **Python Script** mode in the sidebar.
2. Use the file uploader to select **multiple files** at once `.py`, `.txt`, `.json`, `.csv`.
3. If more than one `.py` file is uploaded, a **"Select entry-point"** dropdown appears — choose the file to inject failures into and execute.
4. If a `requirements.txt` is included, FailSafe will **automatically `pip install`** the listed packages inside the sandbox temp-directory before running — no manual setup needed.

> **Tip:** you can test any small project that relies on third-party libraries (e.g. `requests`, `numpy`) by uploading all its files together with a `requirements.txt`.

---

## Optional — Ollama LLM integration

FailSafe works perfectly without Ollama. To enable AI-enhanced suggestions:

```bash
# Install Ollama from https://ollama.com
curl -fsSL https://ollama.com/install.sh | sh

# Pull a lightweight model (pick ONE based on your RAM)
ollama pull mistral        # ~4 GB  — best quality
ollama pull phi3           # ~2 GB  — fastest on low RAM
ollama pull gemma          # ~5 GB  — good balance

# Start the server (runs in the background)
ollama serve
```

Then tick **"Enable AI-enhanced suggestions"** in the Streamlit sidebar.

---

## Google Colab (alternative for low-resource machines)

> ⚠ Colab does NOT support headless browser scraping (Playwright/Selenium).
> FailSafe AI does not scrape — it is fully compatible with Colab free tier.

```python
# In a Colab cell:
!git clone https://github.com/<your-github-handle>/failsafe-ai.git
%cd failsafe-ai
!pip install -r requirements.txt
!pip install pyngrok

from pyngrok import ngrok
import subprocess, threading

def run_app():
    subprocess.run(["streamlit", "run", "app.py",
                    "--server.port=8501", "--server.headless=true"])

threading.Thread(target=run_app, daemon=True).start()

public_url = ngrok.connect(8501)
print(f"FailSafe AI is live at: {public_url}")
```

---

## Project structure

```
failsafe-ai/
│
├── app.py                        ← Streamlit UI entry-point
│
├── injector/
│   ├── __init__.py
│   ├── code_injector.py          ← Injects failures into Python source
│   └── data_injector.py          ← Injects failures into CSV / DataFrame
│
├── sandbox/
│   ├── __init__.py
│   └── executor.py               ← Subprocess sandbox with timeout
│
├── analyzer/
│   ├── __init__.py
│   └── failure_analyzer.py       ← Maps errors → root causes (rule-based)
│
├── suggestions/
│   ├── __init__.py
│   ├── rule_engine.py            ← Deterministic fix suggestions + code hints
│   └── ollama_suggester.py       ← Optional Ollama LLM enhancement
│
├── utils/
│   ├── __init__.py
│   └── logger.py                 ← Structured session logging
│
├── reports/
│   ├── __init__.py
│   ├── report_generator.py       ← Markdown + JSON report builder
│   └── output/                   ← Auto-saved reports land here
│
├── data/
│   ├── sample_script.py          ← Built-in Python script for demos
│   ├── sample_data.csv           ← Built-in CSV dataset for demos
│   └── logs/                     ← Session log files (JSON)
│
├── tests/
│   └── test_failsafe.py          ← Pytest test suite
│
├── requirements.txt
└── README.md
```

---

## Code injection types (Python scripts)

| Injection | Error triggered | Severity |
|-----------|----------------|----------|
| `undefined_variable` | NameError | High |
| `wrong_type_operation` | TypeError | High |
| `file_not_found` | FileNotFoundError | High |
| `index_out_of_range` | IndexError | High |
| `division_by_zero` | ZeroDivisionError | Critical |
| `import_error` | ModuleNotFoundError | Critical |
| `infinite_loop` | TimeoutError (sandbox) | Critical |
| `recursion_error` | RecursionError | Critical |
| `key_error` | KeyError | High |
| `attribute_error` | AttributeError | Medium |

## Data injection types (CSV datasets)

| Injection | What changes | Expected issue |
|-----------|-------------|----------------|
| `missing_values` | ~20 % of cells → NaN | ValueError / TypeError in aggregations |
| `null_column` | Entire column → NaN | Downstream column ops fail |
| `wrong_dtypes` | Numeric column → '42abc' strings | TypeError / ValueError |
| `empty_dataset` | All rows removed | Empty-dataset errors |
| `duplicate_rows` | All rows doubled | Skewed aggregations |
| `wrong_column_name` | Column renamed → `_BROKEN` | KeyError |
| `extra_whitespace` | String columns padded with spaces | Silent join failures |

---
<img width="1805" height="782" alt="image" src="https://github.com/user-attachments/assets/dafad9cb-3cec-46ea-b667-07104d1aa64f" />


## Running tests

```bash
# From the project root
pytest tests/test_failsafe.py -v

# With coverage
pip install pytest-cov
pytest tests/test_failsafe.py -v --cov=. --cov-report=term-missing
```

---

## Sample Markdown report output

```
# FailSafe AI — Simulation Report

**Session ID:** `20240315T142305`
**Generated:** 2024-03-15 14:23:11 UTC

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total tests run | 3 |
| Failures detected | 3 |
| Unexpected passes | 0 |
| Critical failures | 1 |

---

### Test 1: `division_by_zero` — ❌ FAIL

**Scenario:** Appended '1 / 0'. Expected: ZeroDivisionError.

| Field | Value |
|-------|-------|
| Error type | `ZeroDivisionError` |
| Severity | 🔴 critical |
| Category | Arithmetic Error |
| Execution time | 312.4 ms |

**Root cause analysis:**
> A division or modulo operation has zero as its divisor.

**Recommended fix:**
> Guard every division with a denominator != 0 check.
```
<img width="848" height="776" alt="image" src="https://github.com/user-attachments/assets/9f0eb3fd-9d62-4785-a261-bec9c7fce43e" />

---

## Architecture notes

- **No exec() in the main process** — all user code runs in a child subprocess via `subprocess.run()`, so a crash or infinite loop cannot affect the Streamlit server.
- **Stateless injectors** — each injection operates on an independent copy of the original source/data, so tests never interfere with each other.
- **Multi-file project sandbox** — when multiple files are uploaded, `Executor.run_project()` writes them all to a temporary directory. Instead of executing the actual entry-point (which may be a blocking GUI or web server), FailSafe generates a standalone micro-script `_failsafe_test_.py` containing *only* the failure snippet. This script executes inside the project directory, so local imports resolve perfectly, but the user's application never actually blocks the sandbox.
- **Auto-dependency installation** — if a `requirements.txt` is present in the upload, a child `pip install -r …` process runs first (120 s timeout). Any pip failure is surfaced as a `ModuleNotFoundError` in the analysis report rather than silently crashing.
- **Rule table is just a list of dicts** — extending the analyzer with new error patterns requires only adding an entry to `_RULES` in `failure_analyzer.py`.
- **Ollama is fully optional** — the system degrades gracefully to rule-based suggestions if Ollama is unreachable.

---

## Extending FailSafe AI

### Add a new code injection

```python
# injector/code_injector.py

from .code_injector import register, _insert_after_imports

@register("my_new_injection")
def inject_my_failure(source: str) -> tuple[str, str]:
    snippet = '\n# [INJECTED]\nraise RuntimeError("custom failure")\n'
    return _insert_after_imports(source, snippet), "Injected a custom RuntimeError."
```

### Add a new analysis rule

```python
# analyzer/failure_analyzer.py  →  _RULES list

{
    "error_type": "RuntimeError",
    "pattern": r"custom failure",
    "root_cause": "A custom runtime failure was injected.",
    "category": "Custom Failure",
    "severity": "high",
},
```

### Add a new fix suggestion

```python
# suggestions/rule_engine.py  →  _CATALOGUE dict

("Custom Failure", "RuntimeError"): {
    "short_fix": "Wrap the call in a try/except RuntimeError block.",
    "code_hint": "try:\n    risky()\nexcept RuntimeError as e:\n    handle(e)",
    "explanation": "RuntimeError is a generic signal that something went wrong...",
},
```

---

*FailSafe AI — built for portfolio demonstration of fault-injection, sandboxing,
and automated debug assistance. 100 % local, 0 % cloud.*
