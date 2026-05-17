"""
hf_suggester.py
Provides AI-enhanced suggestions using Hugging Face's Inference API.
Perfect for deploying on Hugging Face Spaces where local LLMs (like Ollama) are not needed.
"""

import os
from typing import Iterator

from analyzer.failure_analyzer import AnalysisResult
from suggestions.rule_engine import Suggestion

try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None


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


class HFSuggester:
    """
    Wraps the Hugging Face Inference API to stream responses.
    """

    def __init__(self, model: str = "mistralai/Mistral-7B-Instruct-v0.2", token: str | None = None):
        self.model = model
        self.token = token
        self.client = InferenceClient(model=self.model, token=self.token) if InferenceClient else None

    def is_available(self) -> bool:
        """Check if the huggingface_hub package is installed and token is provided."""
        return InferenceClient is not None and bool(self.token)

    def enhance_stream(self, analysis: AnalysisResult, rule_sugg: Suggestion) -> Iterator[str]:
        """
        Streams enhanced suggestion tokens via Hugging Face API.
        Yields raw text tokens.
        """
        if not self.is_available():
            yield "\n*(Hugging Face integration unavailable — missing HF_TOKEN or huggingface_hub package)*"
            return

        user_prompt = _USER_TEMPLATE.format(
            error_type=analysis.error_type,
            error_message=analysis.error_message[:300],
            category=analysis.category,
            root_cause=analysis.root_cause,
            short_fix=rule_sugg.short_fix,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # We use text_generation instead of chat_completion because chat_completion is supported 
            # fully only by TGI models. text_generation is more universal on the free HF inference API.
            # But let's try chat_completion if available, otherwise fallback.
            try:
                stream = self.client.chat_completion(
                    messages=messages,
                    max_tokens=200,
                    stream=True,
                )
                for chunk in stream:
                    # chunk is a ChatCompletionChunk object
                    token = chunk.choices[0].delta.content
                    if token:
                        yield token
            except Exception as chat_err:
                # Fallback to pure text generation if the model doesn't support chat completion API natively
                prompt = f"<s>[INST] {_SYSTEM_PROMPT}\n\n{user_prompt} [/INST]"
                stream = self.client.text_generation(
                    prompt,
                    max_new_tokens=200,
                    stream=True,
                )
                for token in stream:
                    if token:
                        yield token

        except Exception as e:
            yield f"\n*(Failed to connect to Hugging Face API: {e})*"
