from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

EXPECTED_SCHEMA_KEYS = {
    "matched": list,
    "missing": list,
    "strengths": list,
    "concerns": list,
    "interview_questions": list,
    "recommendation": dict,
}


@dataclass
class EvalResult:
    name: str
    value: float
    passed: bool
    details: str = ""


@dataclass
class ScreeningEvalResults:
    schema_compliance: EvalResult = field(default_factory=lambda: EvalResult("schema_compliance", 0.0, False))
    decision_valid: EvalResult = field(default_factory=lambda: EvalResult("decision_valid", 0.0, False))
    required_fields: EvalResult = field(default_factory=lambda: EvalResult("required_fields", 0.0, False))
    output_completeness: EvalResult = field(default_factory=lambda: EvalResult("output_completeness", 0.0, False))
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_estimate: float = 0.0

    def all_metrics(self) -> Dict[str, float]:
        return {
            self.schema_compliance.name: self.schema_compliance.value,
            self.decision_valid.name: self.decision_valid.value,
            self.required_fields.name: self.required_fields.value,
            self.output_completeness.name: self.output_completeness.value,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_estimate": self.cost_estimate,
        }

    def all_passed(self) -> bool:
        return all([
            self.schema_compliance.passed,
            self.decision_valid.passed,
            self.required_fields.passed,
            self.output_completeness.passed,
        ])


# Rough cost per 1K tokens for common OpenRouter models (USD).
_MODEL_COST_PER_1K_INPUT = {
    "nvidia/nemotron-3-super-120b-a12b:free": 0.0,
    "openai/gpt-4o-mini": 0.00015,
    "openai/gpt-4o": 0.0025,
    "anthropic/claude-3-haiku": 0.00025,
    "anthropic/claude-3-sonnet": 0.003,
    "meta-llama/llama-3-70b-instruct": 0.00035,
    "google/gemini-pro": 0.0005,
}

_MODEL_COST_PER_1K_OUTPUT = {
    "nvidia/nemotron-3-super-120b-a12b:free": 0.0,
    "openai/gpt-4o-mini": 0.0006,
    "openai/gpt-4o": 0.01,
    "anthropic/claude-3-haiku": 0.00125,
    "anthropic/claude-3-sonnet": 0.015,
    "meta-llama/llama-3-70b-instruct": 0.0004,
    "google/gemini-pro": 0.0015,
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate = _MODEL_COST_PER_1K_INPUT.get(model, 0.001)
    output_rate = _MODEL_COST_PER_1K_OUTPUT.get(model, 0.002)
    return (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)


def evaluate_schema_compliance(feedback: dict) -> EvalResult:
    for key, expected_type in EXPECTED_SCHEMA_KEYS.items():
        value = feedback.get(key)
        if value is None or not isinstance(value, expected_type):
            return EvalResult(
                name="schema_compliance",
                value=0.0,
                passed=False,
                details=f"Missing or wrong type for key '{key}': expected {expected_type.__name__}, got {type(value).__name__ if value is not None else 'None'}",
            )
    rec = feedback.get("recommendation", {})
    for sub_key in ("decision", "reason"):
        if sub_key not in rec or not isinstance(rec[sub_key], str):
            return EvalResult(
                name="schema_compliance",
                value=0.0,
                passed=False,
                details=f"Missing or wrong type for recommendation.{sub_key}",
            )
    return EvalResult(name="schema_compliance", value=1.0, passed=True, details="Schema OK")


def evaluate_decision_valid(feedback: dict) -> EvalResult:
    decision = feedback.get("recommendation", {}).get("decision", "")
    valid = decision in ("Proceed", "Reject")
    return EvalResult(
        name="decision_valid",
        value=1.0 if valid else 0.0,
        passed=valid,
        details=f"Decision: {decision}" if valid else f"Invalid decision: {decision}",
    )


def evaluate_required_fields(feedback: dict) -> EvalResult:
    rec = feedback.get("recommendation", {})
    reason = rec.get("reason", "")
    if not isinstance(reason, str) or not reason.strip():
        return EvalResult(
            name="required_fields",
            value=0.0,
            passed=False,
            details="Recommendation reason is empty",
        )
    list_keys = ["matched", "missing", "strengths", "concerns", "interview_questions"]
    for key in list_keys:
        items = feedback.get(key, [])
        if not isinstance(items, list):
            return EvalResult(
                name="required_fields",
                value=0.0,
                passed=False,
                details=f"'{key}' is not a list",
            )
    return EvalResult(name="required_fields", value=1.0, passed=True, details="All required fields present")


def evaluate_output_completeness(feedback: dict) -> EvalResult:
    decision = feedback.get("recommendation", {}).get("decision", "")
    if decision == "Proceed":
        questions = feedback.get("interview_questions", [])
        if not questions or not any(str(q).strip() for q in questions):
            return EvalResult(
                name="output_completeness",
                value=0.5,
                passed=False,
                details="Proceed decision but no interview questions provided",
            )
    if decision == "Reject":
        concerns = feedback.get("concerns", [])
        if not concerns or not any(str(c).strip() for c in concerns):
            return EvalResult(
                name="output_completeness",
                value=0.5,
                passed=False,
                details="Reject decision but no concerns provided",
            )
    return EvalResult(name="output_completeness", value=1.0, passed=True, details="Output complete")


def run_all_evaluators(feedback: dict, model: str = "", input_tokens: int = 0, output_tokens: int = 0, latency_ms: float = 0.0) -> ScreeningEvalResults:
    results = ScreeningEvalResults()
    results.schema_compliance = evaluate_schema_compliance(feedback)
    results.decision_valid = evaluate_decision_valid(feedback)
    results.required_fields = evaluate_required_fields(feedback)
    results.output_completeness = evaluate_output_completeness(feedback)
    results.latency_ms = latency_ms
    results.input_tokens = input_tokens
    results.output_tokens = output_tokens
    results.total_tokens = input_tokens + output_tokens
    results.cost_estimate = _estimate_cost(model, input_tokens, output_tokens)
    return results
