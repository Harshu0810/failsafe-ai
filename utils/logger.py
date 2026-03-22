"""
logger.py
Provides:
  • get_logger(name)  — standard Python logger pre-configured for FailSafe
  • SessionLogger     — accumulates structured log entries per simulation run,
                        serialisable to JSON / markdown for the report generator
"""

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent.parent / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "failsafe.log"


# ── Standard Python logger ────────────────────────────────────────────────────

def get_logger(name: str = "failsafe") -> logging.Logger:
    """
    Return (or create) a logger with:
      • DEBUG → file handler (failsafe.log)
      • WARNING → stderr stream handler
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Stream handler (stderr)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# ── Session Logger ────────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    """One test result entry."""
    timestamp: str
    injection_name: str
    scenario: str
    error_type: str
    error_message: str
    root_cause: str
    category: str
    severity: str
    execution_time_ms: float
    timed_out: bool
    passed: bool
    short_fix: str
    ollama_enhanced: str = ""


class SessionLogger:
    """
    Collects LogEntry objects for the duration of one simulation session.
    Can be serialised to JSON (for storage) or queried for summary stats.
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S"
        )
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.entries: list[LogEntry] = []
        self._logger = get_logger("failsafe.session")

    # ── Recording ─────────────────────────────────────────────────────────

    def record(
        self,
        *,
        injection_name: str,
        scenario: str,
        error_type: str,
        error_message: str,
        root_cause: str,
        category: str,
        severity: str,
        execution_time_ms: float,
        timed_out: bool,
        passed: bool,
        short_fix: str,
        ollama_enhanced: str = "",
    ) -> LogEntry:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            injection_name=injection_name,
            scenario=scenario,
            error_type=error_type,
            error_message=error_message,
            root_cause=root_cause,
            category=category,
            severity=severity,
            execution_time_ms=execution_time_ms,
            timed_out=timed_out,
            passed=passed,
            short_fix=short_fix,
            ollama_enhanced=ollama_enhanced,
        )
        self.entries.append(entry)
        self._logger.debug("Recorded entry: %s → %s", injection_name, error_type or "PASS")
        return entry

    # ── Summary stats ─────────────────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def failed(self) -> int:
        return sum(1 for e in self.entries if not e.passed)

    @property
    def passed_count(self) -> int:
        return sum(1 for e in self.entries if e.passed)

    @property
    def critical_count(self) -> int:
        return sum(1 for e in self.entries if e.severity == "critical")

    def severity_breakdown(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.severity] = counts.get(e.severity, 0) + 1
        return counts

    def category_breakdown(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.category] = counts.get(e.category, 0) + 1
        return counts

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "total": self.total,
            "failed": self.failed,
            "passed": self.passed_count,
            "critical": self.critical_count,
            "severity_breakdown": self.severity_breakdown(),
            "entries": [asdict(e) for e in self.entries],
        }

    def save_json(self, path: str | Path | None = None) -> Path:
        if path is None:
            path = LOGS_DIR / f"session_{self.session_id}.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        self._logger.info("Session log saved → %s", path)
        return path
