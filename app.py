"""
app.py — FailSafe AI  •  System Failure Simulator & Debug Assistant
Streamlit entry-point.  Run with:

    streamlit run app.py
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import io
import os
import sys
import time

# ── third-party ───────────────────────────────────────────────────────────────
import pandas as pd
import streamlit as st

# ── project root on path ──────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── project modules ───────────────────────────────────────────────────────────
from injector.code_injector import CodeInjector
from injector.data_injector import DataInjector
from sandbox.executor import Executor
from analyzer.failure_analyzer import FailureAnalyzer
from suggestions.rule_engine import RuleSuggestionEngine
from suggestions.ollama_suggester import OllamaSuggester
from reports.report_generator import ReportGenerator
from utils.logger import SessionLogger


# ═══════════════════════════════════════════════════════════════════════════════
# Page config  (MUST be first Streamlit call)
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="FailSafe AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Custom CSS — dark industrial aesthetic
# ═══════════════════════════════════════════════════════════════════════════════

CUSTOM_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

  html, body, [class*="css"] {
      font-family: 'IBM Plex Sans', sans-serif;
  }

  /* ── Global background ── */
  .stApp {
      background-color: #0d0f14;
      color: #c9d1d9;
  }

  /* ── Sidebar ── */
  section[data-testid="stSidebar"] {
      background: #111318;
      border-right: 1px solid #21262d;
  }

  /* ── Header strip ── */
  .failsafe-header {
      background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 24px 32px;
      margin-bottom: 24px;
  }
  .failsafe-header h1 {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 2rem;
      font-weight: 600;
      color: #f0f6fc;
      letter-spacing: -0.5px;
      margin: 0 0 4px 0;
  }
  .failsafe-header .tagline {
      font-size: 0.85rem;
      color: #8b949e;
      font-family: 'IBM Plex Mono', monospace;
  }
  .failsafe-header .accent { color: #f78166; }

  /* ── Section headings ── */
  .section-title {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: #8b949e;
      border-bottom: 1px solid #21262d;
      padding-bottom: 8px;
      margin-bottom: 16px;
  }

  /* ── Status badges ── */
  .badge {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 20px;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.5px;
  }
  .badge-fail    { background: rgba(247,129,102,0.15); color: #f78166; border: 1px solid rgba(247,129,102,0.3); }
  .badge-pass    { background: rgba(56,211,159,0.12);  color: #3ddc84; border: 1px solid rgba(56,211,159,0.25); }
  .badge-warn    { background: rgba(255,212,0,0.12);   color: #f1c40f; border: 1px solid rgba(255,212,0,0.2); }
  .badge-crit    { background: rgba(255,77,77,0.15);   color: #ff4d4d; border: 1px solid rgba(255,77,77,0.3); }

  /* ── Test result cards ── */
  .result-card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 20px 24px;
      margin-bottom: 16px;
      font-family: 'IBM Plex Sans', sans-serif;
  }
  .result-card.fail { border-left: 3px solid #f78166; }
  .result-card.pass { border-left: 3px solid #3ddc84; }
  .result-card h3 {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.9rem;
      margin: 0 0 12px 0;
      color: #f0f6fc;
  }
  .result-card .meta {
      font-size: 0.78rem;
      color: #8b949e;
      font-family: 'IBM Plex Mono', monospace;
  }
  .result-card .root-cause {
      font-size: 0.82rem;
      color: #c9d1d9;
      background: #0d1117;
      border: 1px solid #21262d;
      border-radius: 4px;
      padding: 10px 14px;
      margin: 10px 0;
  }
  .result-card .fix-text {
      font-size: 0.82rem;
      color: #79c0ff;
  }

  /* ── Summary metrics ── */
  .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 24px;
  }
  .metric-box {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 16px;
      text-align: center;
  }
  .metric-box .number {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 2rem;
      font-weight: 600;
      color: #f0f6fc;
      line-height: 1;
  }
  .metric-box .label {
      font-size: 0.7rem;
      color: #8b949e;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-top: 4px;
  }
  .metric-box.crit .number { color: #ff4d4d; }
  .metric-box.fail .number { color: #f78166; }
  .metric-box.pass .number { color: #3ddc84; }

  /* ── Code blocks ── */
  .stCodeBlock, code {
      font-family: 'IBM Plex Mono', monospace !important;
      font-size: 0.78rem !important;
  }

  /* ── Progress / spinner ── */
  .stSpinner > div { border-top-color: #f78166 !important; }

  /* ── Buttons ── */
  .stButton > button {
      background: #f78166;
      color: #0d0f14;
      font-family: 'IBM Plex Mono', monospace;
      font-weight: 600;
      border: none;
      border-radius: 4px;
      padding: 8px 24px;
      letter-spacing: 0.5px;
      transition: background 0.15s;
  }
  .stButton > button:hover { background: #ff9980; color: #0d0f14; }

  /* ── Expander ── */
  .streamlit-expanderHeader {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.8rem;
      color: #8b949e;
  }

  /* ── File uploader ── */
  .stFileUploader {
      background: #161b22;
      border: 1px dashed #30363d;
      border-radius: 6px;
  }

  /* ── Multiselect tags ── */
  .stMultiSelect [data-baseweb="tag"] {
      background-color: rgba(247,129,102,0.15) !important;
      color: #f78166 !important;
  }

  /* ── Dividers ── */
  hr { border-color: #21262d !important; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: #0d0f14; }
  ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

SANDBOX_TIMEOUT = 8  # seconds

SEV_COLOR = {
    "critical": "#ff4d4d",
    "high": "#f78166",
    "medium": "#f1c40f",
    "low": "#3ddc84",
}
SEV_ICON = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _get_executor() -> Executor:
    return Executor(timeout_seconds=SANDBOX_TIMEOUT)


@st.cache_resource
def _get_analyzer() -> FailureAnalyzer:
    return FailureAnalyzer()


@st.cache_resource
def _get_rule_engine() -> RuleSuggestionEngine:
    return RuleSuggestionEngine()


@st.cache_resource
def _get_ollama(model: str) -> OllamaSuggester:
    return OllamaSuggester(model=model)


def _badge(text: str, kind: str) -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'


# ═══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown(
        '<p class="section-title">⚡ FailSafe AI</p>',
        unsafe_allow_html=True,
    )

    st.markdown("**Mode**")
    mode = st.radio(
        "Input type",
        ["Python Script", "CSV Dataset"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("**Sandbox Settings**")
    timeout_val = st.slider("Execution timeout (s)", 3, 20, SANDBOX_TIMEOUT)

    st.markdown("---")
    st.markdown("**Ollama (optional)**")
    use_ollama = st.checkbox("Enable AI-enhanced suggestions", value=False)
    ollama_model = st.selectbox(
        "Model",
        ["mistral", "phi3", "llama3", "gemma"],
        disabled=not use_ollama,
    )
    if use_ollama:
        ollama = _get_ollama(ollama_model)
        ollama_ok = ollama.is_available()
        if ollama_ok:
            st.success(f"✓ Ollama connected ({ollama_model})")
        else:
            st.warning("⚠ Ollama not reachable — rule-based only")
            use_ollama = False

    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.7rem;color:#8b949e;font-family:\'IBM Plex Mono\',monospace;">'
        "CPU-only · Local execution · No cloud APIs</p>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown(
    """
    <div class="failsafe-header">
      <h1>⚡ FailSafe<span class="accent"> AI</span></h1>
      <p class="tagline">// System Failure Simulator &amp; Debug Assistant //
         inject → observe → diagnose → fix</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Input section
# ═══════════════════════════════════════════════════════════════════════════════

col_input, col_inject = st.columns([3, 2], gap="large")

with col_input:
    st.markdown('<p class="section-title">01 — Input</p>', unsafe_allow_html=True)

    if mode == "Python Script":
        uploaded_files = st.file_uploader(
            "Upload project files (.py, .txt, .json, .csv)",
            type=["py", "txt", "json", "csv"],
            accept_multiple_files=True,
            key="py_upload",
            help="Upload a single .py file **or** an entire project (multiple .py files + requirements.txt + helpers).",
        )
        default_src = open(
            os.path.join(ROOT, "data", "sample_script.py"), encoding="utf-8"
        ).read()

        # ── Build a dict of filename → bytes for all uploads ──────────────────
        project_files: dict[str, bytes] = {}
        project_mode = False  # True = multi-file project, False = single script
        source_code = default_src
        entry_point: str | None = None

        if uploaded_files:
            for uf in uploaded_files:
                project_files[uf.name] = uf.read()

            py_files = [n for n in project_files if n.endswith(".py")]
            has_requirements = "requirements.txt" in project_files

            if len(py_files) > 1:
                project_mode = True
                entry_point = st.selectbox(
                    "🎯 Select entry-point script (the file to execute)",
                    options=py_files,
                    help="This is the file FailSafe will inject failures into and run.",
                )
                if has_requirements:
                    st.info(
                        "📦 `requirements.txt` detected — dependencies will be installed "
                        "automatically in the sandbox before execution.",
                        icon="📦",
                    )
                st.success(
                    f"Loaded **{len(project_files)}** file(s) — "
                    f"entry point: **{entry_point}**"
                )
                # For the injector / preview, use the entry-point source
                source_code = project_files[entry_point].decode("utf-8")

            else:
                # Single .py file — classic mode
                entry_point = py_files[0] if py_files else None
                if entry_point:
                    source_code = project_files[entry_point].decode("utf-8")
                    st.success(
                        f"Loaded: **{entry_point}**  ({len(source_code):,} chars)"
                    )
        else:
            st.info("No file uploaded — using built-in sample script.")

        with st.expander("Preview source code", expanded=False):
            st.code(source_code, language="python")

    else:  # CSV
        uploaded = st.file_uploader(
            "Upload a .csv file", type=["csv"], key="csv_upload"
        )
        default_csv = os.path.join(ROOT, "data", "sample_data.csv")

        if uploaded:
            csv_bytes = uploaded.read()
            df = pd.read_csv(io.BytesIO(csv_bytes))
            st.success(f"Loaded: **{uploaded.name}**  ({df.shape[0]} rows × {df.shape[1]} cols)")
        else:
            st.info("No file uploaded — using built-in sample dataset.")
            df = pd.read_csv(default_csv)
            csv_bytes = open(default_csv, "rb").read()

        with st.expander("Preview dataset", expanded=False):
            st.dataframe(df.head(10), width='stretch')

with col_inject:
    st.markdown('<p class="section-title">02 — Failure Injections</p>', unsafe_allow_html=True)

    if mode == "Python Script":
        available = CodeInjector("").available_injections()
        default_sel = ["undefined_variable", "file_not_found", "division_by_zero"]
    else:
        available = DataInjector(df=pd.DataFrame({"x": [1]})).available_injections()
        default_sel = ["missing_values", "wrong_dtypes", "empty_dataset"]

    selected_injections = st.multiselect(
        "Select failure types to inject",
        options=available,
        default=[i for i in default_sel if i in available],
        help="Each injection runs as an independent test case.",
    )

    st.markdown(
        f'<p style="color:#8b949e;font-size:0.78rem;font-family:\'IBM Plex Mono\',monospace;">'
        f"{len(selected_injections)} injection(s) selected → {len(selected_injections)} test(s) will run</p>",
        unsafe_allow_html=True,
    )

    run_button = st.button(
        "▶  Run Simulation",
        disabled=len(selected_injections) == 0,
        width='stretch',
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Simulation engine
# ═══════════════════════════════════════════════════════════════════════════════

if run_button:
    st.markdown("---")
    st.markdown('<p class="section-title">03 — Simulation Results</p>', unsafe_allow_html=True)

    executor = Executor(timeout_seconds=timeout_val)
    analyzer = _get_analyzer()
    rule_engine = _get_rule_engine()
    session = SessionLogger()

    exec_results = []
    analysis_results = []
    suggestions = []

    progress = st.progress(0, text="Initialising simulation…")
    status_area = st.empty()

    n = len(selected_injections)

    for idx, injection_name in enumerate(selected_injections):
        pct = int((idx / n) * 100)
        progress.progress(pct, text=f"Running test {idx + 1}/{n}: `{injection_name}` …")

        # ── Inject ────────────────────────────────────────────────────────
        if mode == "Python Script":
            ci = CodeInjector(source_code)
            inj_results = ci.run([injection_name])
            inj = inj_results[0]
            modified_source = inj["modified_source"]
            scenario = inj["scenario"]

            if project_mode and entry_point:
                # ── Multi-file project mode ──────────────────────────
                # Do NOT run the user's entry-point — it may be a web
                # server, GUI, or long-running daemon that blocks.
                # Instead, generate a tiny *standalone* test script
                # containing only the failure snippet and run THAT
                # inside the project directory (so local imports work).

                # Extract only the injected snippet (from # [INJECTED] onward)
                lines = modified_source.splitlines()
                inject_start = None
                for li, line in enumerate(lines):
                    if "# [INJECTED]" in line:
                        inject_start = li
                        break

                if inject_start is not None:
                    standalone_src = "\n".join(lines[inject_start:]) + "\n"
                else:
                    # Fallback — run the full modified source
                    standalone_src = modified_source

                injected_project = dict(project_files)
                test_filename = "_failsafe_test_.py"
                injected_project[test_filename] = standalone_src.encode("utf-8")

                exec_result = executor.run_project(
                    files=injected_project,
                    entry_point=test_filename,
                    injection_name=injection_name,
                    scenario=scenario,
                )
            else:
                exec_result = executor.run(
                    modified_source,
                    injection_name=injection_name,
                    scenario=scenario,
                )

        else:  # CSV
            di = DataInjector(df=df)
            inj_results = di.run([injection_name])
            inj = inj_results[0]
            modified_df = inj["modified_df"]
            scenario = inj["scenario"]

            # Build a small analysis script for the modified CSV
            analysis_script = """
import pandas as pd, numpy as np, sys

df = pd.read_csv(INPUT_CSV)
print(f"Shape: {df.shape}")
print(f"Dtypes:\\n{df.dtypes}")
print(f"Null counts:\\n{df.isnull().sum()}")
print(f"Numeric stats:")

numeric_cols = df.select_dtypes(include=[np.number]).columns
if len(numeric_cols):
    for col in numeric_cols:
        vals = pd.to_numeric(df[col], errors='raise')
        print(f"  {col}: mean={vals.mean():.2f}")
else:
    print("  No numeric columns found.")

if df.empty:
    raise ValueError("Dataset is empty — cannot proceed with analysis.")

print("Analysis complete.")
"""
            # Write modified df to bytes
            buf = io.StringIO()
            modified_df.to_csv(buf, index=False)
            modified_csv_bytes = buf.getvalue().encode("utf-8")

            exec_result = executor.run_csv_script(
                analysis_script,
                modified_csv_bytes,
                injection_name=injection_name,
                scenario=scenario,
            )

        exec_results.append(exec_result)

        # ── Analyse ───────────────────────────────────────────────────────
        analysis = analyzer.analyze(exec_result)
        analysis_results.append(analysis)

        # ── Suggest ───────────────────────────────────────────────────────
        suggestion = rule_engine.suggest(analysis)
        if use_ollama and ollama_ok:
            ollama_instance = _get_ollama(ollama_model)
            ollama_instance.enhance(analysis, suggestion)
        suggestions.append(suggestion)

        # ── Log ───────────────────────────────────────────────────────────
        session.record(
            injection_name=injection_name,
            scenario=scenario,
            error_type=analysis.error_type,
            error_message=analysis.error_message,
            root_cause=analysis.root_cause,
            category=analysis.category,
            severity=analysis.severity,
            execution_time_ms=analysis.execution_time_ms,
            timed_out=analysis.timed_out,
            passed=analysis.passed,
            short_fix=suggestion.short_fix,
            ollama_enhanced=suggestion.ollama_enhanced,
        )

    progress.progress(100, text="Simulation complete ✓")
    time.sleep(0.3)
    progress.empty()

    # ── Summary metrics ───────────────────────────────────────────────────────

    total = session.total
    failed = session.failed
    passed_c = session.passed_count
    critical = session.critical_count

    st.markdown(
        f"""
        <div class="metric-grid">
          <div class="metric-box">
            <div class="number">{total}</div>
            <div class="label">Tests run</div>
          </div>
          <div class="metric-box fail">
            <div class="number">{failed}</div>
            <div class="label">Failures</div>
          </div>
          <div class="metric-box pass">
            <div class="number">{passed_c}</div>
            <div class="label">Passes</div>
          </div>
          <div class="metric-box crit">
            <div class="number">{critical}</div>
            <div class="label">Critical</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Per-test result cards ─────────────────────────────────────────────────

    for i, (ar, sug, er) in enumerate(
        zip(analysis_results, suggestions, exec_results), start=1
    ):
        card_class = "pass" if ar.passed else "fail"
        status_badge = _badge("PASS", "pass") if ar.passed else _badge("FAIL", "fail")
        sev_badge = _badge(
            f"{SEV_ICON.get(ar.severity, '⚪')} {ar.severity}",
            "crit" if ar.severity == "critical" else
            "fail" if ar.severity == "high" else
            "warn" if ar.severity == "medium" else "pass",
        )

        st.markdown(
            f"""
            <div class="result-card {card_class}">
              <h3>Test {i}: <code>{ar.injection_name}</code>
                &nbsp;{status_badge}&nbsp;{sev_badge}
              </h3>
              <div class="meta">
                scenario: {ar.scenario[:120]}{'…' if len(ar.scenario) > 120 else ''}
              </div>
              <div class="meta" style="margin-top:6px;">
                error: <strong style="color:#f78166;">{ar.error_type or 'None'}</strong>
                &nbsp;|&nbsp; {ar.execution_time_ms:.0f} ms
                {'&nbsp;|&nbsp; ⏱ TIMED OUT' if ar.timed_out else ''}
              </div>
              <div class="root-cause">
                <strong style="color:#8b949e;font-size:0.7rem;letter-spacing:1px;
                              text-transform:uppercase;">Root Cause</strong><br/>
                {ar.root_cause}
              </div>
              <div class="fix-text">
                <strong>Fix:</strong> {sug.short_fix}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(f"▸ Details — Test {i}: {ar.injection_name}"):
            det_col1, det_col2 = st.columns(2)

            with det_col1:
                st.markdown("**Error message**")
                st.code(ar.error_message or "(none)", language="text")

                st.markdown("**Full traceback**")
                st.code(ar.traceback or "(none)", language="text")

                if er.stdout:
                    st.markdown("**stdout**")
                    st.code(er.stdout, language="text")

            with det_col2:
                st.markdown("**Code hint**")
                st.code(sug.code_hint, language="python")

                st.markdown("**Explanation**")
                st.markdown(
                    f'<div class="root-cause">{sug.explanation}</div>',
                    unsafe_allow_html=True,
                )

                if sug.ollama_enhanced:
                    st.markdown("**🤖 Ollama-enhanced suggestion**")
                    st.markdown(
                        f'<div class="root-cause" style="border-color:#58a6ff;">'
                        f'{sug.ollama_enhanced}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Report download ───────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown('<p class="section-title">04 — Report</p>', unsafe_allow_html=True)

    rg = ReportGenerator(session)
    md_report = rg.to_markdown()
    json_report = rg.to_json()

    dl_col1, dl_col2, dl_col3 = st.columns(3)

    with dl_col1:
        st.download_button(
            label="⬇ Download Markdown Report",
            data=md_report,
            file_name=f"failsafe_report_{session.session_id}.md",
            mime="text/markdown",
            width='stretch',
        )

    with dl_col2:
        st.download_button(
            label="⬇ Download JSON Report",
            data=json_report,
            file_name=f"failsafe_report_{session.session_id}.json",
            mime="application/json",
            width='stretch',
        )

    with dl_col3:
        # Save to disk silently
        saved = rg.save(output_dir=os.path.join(ROOT, "reports", "output"))
        st.success(f"Reports auto-saved → {saved['markdown'].name}")

    with st.expander("Preview Markdown Report"):
        st.markdown(md_report)

# ═══════════════════════════════════════════════════════════════════════════════
# Footer
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown(
    """
    <p style="text-align:center;font-size:0.7rem;color:#484f58;
              font-family:'IBM Plex Mono',monospace;">
      FailSafe AI &nbsp;•&nbsp; fully local &nbsp;•&nbsp; CPU-only &nbsp;•&nbsp;
      no paid APIs &nbsp;•&nbsp; open source
    </p>
    """,
    unsafe_allow_html=True,
)
