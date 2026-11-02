"""LLM quality judge for the screening retry loop.

After the deterministic structural gate (`evaluators.py`) passes, this judge
scores the generated feedback on a 0-10 scale and returns actionable feedback
that is injected into the retry generation prompt. Faithfulness is folded in
as a `groundedness` dimension so a single LLM call covers quality + fidelity.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from pydantic import BaseModel, Field

from app.eval.llm import get_judge

logger = logging.getLogger(__name__)

JUDGE_DIMENSIONS = [
    "completeness",
    "relevance",
    "specificity",
    "actionability",
    "groundedness",
]


class JudgeVerdict(BaseModel):
    """Structured output of the quality judge (0-10 scale)."""

    score: int = Field(ge=0, le=10)
    dimension_scores: Dict[str, int] = Field(
        description=(
            "Per-dimension scores 0-10 for completeness, relevance, specificity, "
            "actionability, groundedness"
        )
    )
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    regeneration_instructions: str = Field(
        description=(
            "Short, actionable instruction for the generator to improve the next "
            "attempt, addressing the weaknesses above."
        )
    )


def build_judge_prompt(job_description: str, resume_text: str, feedback: dict) -> str:
    """Prompt that scores one generated feedback against job + CV."""
    import json

    return f"""
You are a strict quality judge for an AI recruitment screening pipeline.
A generator produced structured candidate feedback for a job. Evaluate its quality.

Score the feedback 0-10 overall AND per-dimension (0-10):
- completeness: every section is filled appropriately. For a "Proceed" decision there
  must be interview questions; for "Reject" there must be concerns.
- relevance: the matched/missing lists accurately reflect the job requirements and the
  candidate's CV.
- specificity: claims are concrete and evidence-based, not generic filler.
- actionability: interview questions are targeted at this candidate and answerable.
- groundedness: every claim is supported by the CV. Detect INTERNAL CONTRADICTIONS
  (e.g. the same skill appearing in both matched and missing) and unverifiable
  claims. Only mark groundedness low when the CV contradicts or does not support a
  claim — never penalize for missing CV content.

Use the strengths/weaknesses/recommendations to drive improvement. Write
regeneration_instructions as a compact instruction the generator can follow verbatim
to fix the weakest dimensions.

Return ONLY valid JSON matching this schema:
{{
  "score": <int 0-10>,
  "dimension_scores": {{
    "completeness": <int 0-10>,
    "relevance": <int 0-10>,
    "specificity": <int 0-10>,
    "actionability": <int 0-10>,
    "groundedness": <int 0-10>
  }},
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommendations": ["..."],
  "regeneration_instructions": "..."
}}

Job Description:
{job_description}

Candidate CV:
{resume_text}

Generated Feedback:
{json.dumps(feedback, indent=2, default=str)}

JSON:
"""


async def score_feedback(
    job_description: str,
    resume_text: str,
    feedback: dict,
) -> JudgeVerdict | None:
    """Score a feedback dict with the judge LLM.

    Returns `None` when the judge call fails (logged as missing value).
    """
    prompt = build_judge_prompt(job_description, resume_text, feedback)
    try:
        judge = get_judge()
        result = await judge.a_generate(prompt, schema=JudgeVerdict)
        if isinstance(result, JudgeVerdict):
            return result
        return JudgeVerdict.model_validate(result)
    except Exception as e:
        logger.warning("Quality judge failed: %s", e)
        return None


def build_critique_text(verdict: JudgeVerdict) -> str:
    """Turn a judge verdict into the critique section for the retry prompt."""
    parts = [
        "A quality judge reviewed your previous attempt. Address every point below "
        "in your revised output.",
        "",
        "Weaknesses:",
        *[f"- {w}" for w in verdict.weaknesses],
        "",
        "Recommendations:",
        *[f"- {r}" for r in verdict.recommendations],
        "",
        f"Instructions: {verdict.regeneration_instructions}",
    ]
    return "\n".join(parts)


def build_structural_critique_text(failures: list[str]) -> str:
    """Turn failing structural checks into the critique for the retry prompt."""
    parts = [
        "Your previous attempt failed validation. Fix all of the following:",
        "",
        *[f"- {f}" for f in failures],
        "",
        "Return valid JSON matching the requested schema exactly. "
        "decision must be Proceed or Reject and reason must be non-empty. "
        "For Proceed, provide interview_questions; for Reject, provide concerns.",
    ]
    return "\n".join(parts)
