"""
ollama_suggester.py
Optional enhancement layer: sends a compact prompt to a local Ollama instance
and returns a natural-language explanation that improves on the rule-based text.

Design choices for low-resource machines:
  • Uses the smallest available model (default: mistral or phi3)
  • max_tokens capped at 200 to limit RAM pressure
  • Streaming is NOT used — single blocking call is simpler and more reliable
  • The module degrades gracefully: if Ollama is unavailable it returns ""
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from analyzer.failure_analyzer import AnalysisResult
from suggestions.rule_engine import Suggestion


# ── Prompt template ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a senior Python engineer. "
    "Given a runtime error and a rule-based suggestion, write a concise "
    "(3–5 sentence) improvement that is more readable, explains the root cause "
    "in plain English, and ends with one actionable next step. "
    "Do NOT include code blocks. Keep it under 120 words."
)

_USER_TEMPLATE = """\
Error type    : {error_type}
Error message : {error_message}
Category      : {category}
Root cause    : {root_cause}
Rule-based fix: {short_fix}

Improve this explanation for a developer reading a failure report."""


# ── Ollama client ─────────────────────────────────────────────────────────────

class OllamaSuggester:
    """
    Wraps the Ollama REST API (/api/generate).

    Parameters
    ----------
    model : str
        Ollama model tag to use.  'mistral' and 'phi3' work well on 8 GB RAM.
    base_url : str
        URL of the Ollama server (default: http://localhost:11434).
    timeout : int
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "mistral",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── Public API ────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if the Ollama server responds to a health ping."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    def enhance(self, analysis: AnalysisResult, suggestion: Suggestion) -> str:
        """
        Return an LLM-enhanced explanation string, or "" on failure.
        The suggestion object is mutated in-place (ollama_enhanced field).
        """
        if not self.is_available():
            return ""

        prompt = _USER_TEMPLATE.format(
            error_type=analysis.error_type or "Unknown",
            error_message=analysis.error_message or "N/A",
            category=analysis.category,
            root_cause=analysis.root_cause,
            short_fix=suggestion.short_fix,
        )

        payload = {
            "model": self.model,
            "system": _SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 200,   # max tokens — keep RAM usage low
                "temperature": 0.3,   # low temperature → more deterministic
            },
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                enhanced = body.get("response", "").strip()
        except Exception as exc:
            # Degrade gracefully — caller can still show rule-based suggestion
            enhanced = ""

        suggestion.ollama_enhanced = enhanced
        return enhanced

    def enhance_batch(
        self,
        analyses: list[AnalysisResult],
        suggestions: list[Suggestion],
    ) -> None:
        """Enhance a list of (analysis, suggestion) pairs in-place."""
        for analysis, suggestion in zip(analyses, suggestions):
            self.enhance(analysis, suggestion)
