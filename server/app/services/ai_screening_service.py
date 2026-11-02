from typing import Callable, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.config import get_settings
from app.models.ai_screening import AIScreening
from app.models.ai_screening_run import AIScreeningRun
from app.models.job import Job
from app.models.job_application import JobApplication
from app.models.candidate_cv import CandidateCV
from app.services.job_service import build_job_embedding_text
import litellm
import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List

logger = logging.getLogger(__name__)

settings = get_settings()

def _extract_usage(response) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    try:
        if hasattr(response, "usage") and response.usage is not None:
            input_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(response.usage, "completion_tokens", 0) or 0
    except Exception:
        pass
    return input_tokens, output_tokens


@dataclass
class AttemptResult:
    """One generation attempt and its evaluation."""
    attempt: int
    feedback: Dict[str, Any]
    structural_passed: bool
    structural_failures: List[str]
    judge_score: Optional[float]
    passed: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int
    judge_verdict: Any = None


@dataclass
class FeedbackResult:
    """Result of the generate -> judge -> retry loop for one candidate."""
    feedback: Dict[str, Any]
    passed: bool
    attempts: List[AttemptResult] = field(default_factory=list)
    best_attempt: Optional[int] = None
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    judge_model: str = ""

def reciprocal_rank_fusion(
    result_lists: list[list[tuple]],
    k: int = 60,
) -> list[tuple]:
    """Merge ranked result lists using Reciprocal Rank Fusion (RRF).

    Each result list is ordered by rank and contains tuples of
    (application, cv, semantic_distance). Items present in multiple lists
    accumulate an RRF score of sum(1 / (k + rank)). The k constant controls
    how much top-ranked results are trusted; higher k weights all ranks more
    equally.
    """
    rrf_scores: Dict[UUID, float] = {}
    results_by_id: Dict[UUID, tuple] = {}

    for result_list in result_lists:
        for rank, item in enumerate(result_list, start=1):
            application = item[0]
            rrf_scores[application.id] = rrf_scores.get(application.id, 0.0) + 1.0 / (k + rank)
            results_by_id[application.id] = item

    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    return [
        (*results_by_id[application_id], rrf_scores[application_id])
        for application_id in sorted_ids
    ]

def _format_cv_text(resume_json: Dict) -> str:
    """Convert the JSONB resume_text dict into a readable text block for LLM prompts."""
    parts = []
    parts.append(f"Candidate Summary: {resume_json.get('candidate_summary', '')}")
    
    skills = resume_json.get('skills', [])
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
    
    education = resume_json.get('education', [])
    if education:
        parts.append(f"Education: {'; '.join(education)}")
    
    work_experiences = resume_json.get('work_experiences', [])
    if work_experiences:
        parts.append(f"Work Experiences: {'; '.join(work_experiences)}")
    
    projects = resume_json.get('projects', [])
    if projects:
        parts.append(f"Projects: {'; '.join(projects)}")
    
    certifications = resume_json.get('certifications', [])
    if certifications:
        parts.append(f"Certifications: {'; '.join(certifications)}")
    
    return "\n\n".join(parts)

def _format_job_description(job_json: Dict) -> str:
    """Convert the JSONB job description dict into a readable text block."""
    parts = []
    parts.append(f"Description: {job_json.get('description', '')}")
    
    requirements = job_json.get('requirements', [])
    if requirements:
        parts.append(f"Requirements: {'; '.join(requirements)}")
    
    jobdesk = job_json.get('jobdesk', [])
    if jobdesk:
        parts.append(f"Jobdesk: {'; '.join(jobdesk)}")
    
    benefits = job_json.get('benefits', [])
    if benefits:
        parts.append(f"Benefits: {'; '.join(benefits)}")
    
    return "\n\n".join(parts)

class AIScreeningService:
    _on_feedback_callback: Callable | None = None

    def _extract_json_content(self, content: str) -> str:
        content = content.strip()
        if content.startswith("```json"):
            return content[7:-3].strip()
        if content.startswith("```"):
            return content[3:-3].strip()
        return content

    def _normalize_feedback(self, feedback: Dict) -> Dict:
        required_list_keys = [
            "matched",
            "missing",
            "strengths",
            "concerns",
            "interview_questions",
        ]
        recommendation = feedback.get("recommendation")

        if not isinstance(recommendation, dict):
            raise ValueError("AI feedback is missing recommendation object")

        decision = recommendation.get("decision")
        reason = recommendation.get("reason")
        if decision not in {"Proceed", "Reject"}:
            raise ValueError("AI feedback recommendation decision must be Proceed or Reject")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("AI feedback recommendation reason is required")

        normalized = {
            "matched": [],
            "missing": [],
            "strengths": [],
            "concerns": [],
            "interview_questions": [],
            "recommendation": {
                "decision": decision,
                "reason": reason.strip(),
            },
        }

        for key in required_list_keys:
            value = feedback.get(key, [])
            if not isinstance(value, list):
                raise ValueError(f"AI feedback {key} must be a list")
            normalized[key] = [str(item).strip() for item in value if str(item).strip()]

        return normalized

    async def _generate_feedback(self, job_description: str, resume_text: str, critique: str | None = None) -> Dict:
        critique_section = f"\n\nPrevious attempt feedback:\n{critique}" if critique else ""
        prompt = f"""
You are an AI recruiter.
Compare this candidate to the job and return only valid JSON matching this exact schema:
{{
  "matched": ["<requirements or signals from the job that the candidate matches>"],
  "missing": ["<important requirements or signals not found in the candidate CV>"],
  "strengths": ["<candidate strengths relevant to this role>"],
  "concerns": ["<specific hiring concerns or risks>"],
  "interview_questions": ["<targeted interview questions to validate the fit>"],
  "recommendation": {{
    "decision": "Proceed | Reject",
    "reason": "<short reason for the decision>"
  }}
}}

Use "Proceed" only when the candidate appears worth interviewing. Use "Reject" otherwise.
Return JSON only, with no markdown blocks.
{critique_section}
Job Description:
{job_description}

Candidate CV:
{resume_text}
"""
        try:
            response = await litellm.acompletion(
                model=f"openrouter/{settings.LLM_MODEL}",
                messages=[{"role": "user", "content": prompt}],
                api_key=settings.OPENROUTER_API_KEY,
            )
            content = response.choices[0].message.content or ""
            parsed = json.loads(self._extract_json_content(content))
            if not isinstance(parsed, dict):
                raise ValueError("AI feedback response must be a JSON object")
            feedback = self._normalize_feedback(parsed)
            if self._on_feedback_callback is not None:
                self._on_feedback_callback(feedback, response)
            return feedback
        except Exception as e:
            raise ValueError(f"AI feedback generation failed: {e}") from e

    async def _generate_feedback_with_retry(
        self,
        job_description: str,
        resume_text: str,
    ) -> FeedbackResult:
        """Generate -> judge -> retry loop for one candidate.

        Structural gate (rule-based) runs first; the LLM quality judge runs only
        when the structural gate passes (kept as missing value otherwise). Retries
        up to `EVAL_RETRY_MAX` times injecting the judge's critique, and returns
        the best-so-far attempt when the threshold is never reached.
        """
        from app.eval.evaluators import run_all_evaluators
        from app.eval.judge import (
            build_critique_text,
            build_structural_critique_text,
            score_feedback,
        )

        if not settings.EVAL_RETRY_ENABLED:
            start = time.perf_counter()
            feedback = await self._generate_feedback(job_description, resume_text)
            latency_ms = (time.perf_counter() - start) * 1000
            structural = run_all_evaluators(feedback, model=settings.LLM_MODEL, latency_ms=latency_ms)
            return FeedbackResult(
                feedback=feedback,
                passed=True,
                total_latency_ms=latency_ms,
                total_tokens=structural.total_tokens,
                judge_model=settings.EVAL_LLM_MODEL or settings.LLM_MODEL,
            )

        max_retries = settings.EVAL_RETRY_MAX
        threshold = settings.EVAL_RETRY_THRESHOLD
        attempts: List[AttemptResult] = []
        best_index: Optional[int] = None
        best_score: Optional[float] = None
        critique: Optional[str] = None
        total_tokens = 0
        total_latency_ms = 0.0
        attempt_limit = max_retries + 1  # initial generation + up to N retries

        existing_callback = self._on_feedback_callback
        captor: dict = {}

        def _capturing_callback(feedback, response):
            input_tokens, output_tokens = _extract_usage(response)
            captor["input_tokens"] = input_tokens
            captor["output_tokens"] = output_tokens
            if existing_callback is not None:
                existing_callback(feedback, response)

        self._on_feedback_callback = _capturing_callback
        try:
            for attempt in range(1, attempt_limit + 1):
                start = time.perf_counter()
                try:
                    feedback = await self._generate_feedback(job_description, resume_text, critique=critique)
                except Exception as e:
                    logger.warning("Generation failed on attempt %s: %s", attempt, e)
                    if attempt == attempt_limit:
                        raise
                    critique = f"Your previous attempt failed to produce valid output. Fix this: {e}"
                    continue
                latency_ms = (time.perf_counter() - start) * 1000
                input_tokens = captor.pop("input_tokens", 0)
                output_tokens = captor.pop("output_tokens", 0)
                total_tokens += input_tokens + output_tokens
                total_latency_ms += latency_ms

                structural = run_all_evaluators(
                    feedback,
                    model=settings.LLM_MODEL,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                )
                failures = [
                    name
                    for name in ("schema_compliance", "decision_valid", "required_fields", "output_completeness")
                    if not getattr(structural, name).passed
                ]
                structural_passed = structural.all_passed()

                judge_verdict = None
                if structural_passed:
                    judge_verdict = await score_feedback(job_description, resume_text, feedback)
                judge_score = judge_verdict.score if judge_verdict is not None else None
                passed = judge_score is not None and judge_score >= threshold

                attempts.append(AttemptResult(
                    attempt=attempt,
                    feedback=feedback,
                    structural_passed=structural_passed,
                    structural_failures=failures,
                    judge_score=judge_score,
                    passed=passed,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    judge_verdict=judge_verdict,
                ))

                if passed:
                    best_index = len(attempts) - 1
                    break

                if judge_score is not None and (best_score is None or judge_score > best_score):
                    best_score = judge_score
                    best_index = len(attempts) - 1

                critique = (
                    build_critique_text(judge_verdict)
                    if judge_verdict is not None
                    else (build_structural_critique_text(failures) if failures else None)
                )
        finally:
            self._on_feedback_callback = existing_callback

        if best_index is None:
            best_index = len(attempts) - 1
        final = attempts[best_index]
        return FeedbackResult(
            feedback=final.feedback,
            passed=final.passed,
            attempts=attempts,
            best_attempt=final.attempt,
            total_latency_ms=total_latency_ms,
            total_tokens=total_tokens,
            judge_model=settings.EVAL_LLM_MODEL or settings.LLM_MODEL,
        )

    async def _rerank(self, query: str, documents: list[str], top_n: int) -> list[dict]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/rerank",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.RERANK_MODEL,
                        "query": query,
                        "documents": documents,
                        "top_n": top_n,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
        except Exception as e:
            logger.warning("Rerank failed, skipping rerank scores: %s", e)
            return []

    async def _semantic_candidates(
        self,
        db: AsyncSession,
        job: Job,
        limit: int | None = None,
    ) -> list[tuple]:
        """Find candidates by vector similarity using cosine distance."""
        distance = CandidateCV.embedding.cosine_distance(job.embedding)
        stmt = (
            select(JobApplication, CandidateCV, distance.label("distance"))
            .join(CandidateCV, JobApplication.cv_id == CandidateCV.id)
            .where(
                JobApplication.job_id == job.id,
                CandidateCV.embedding.isnot(None),
                JobApplication.status.in_(["applied"]),
            )
            .order_by(distance)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return [(application, cv, float(dist)) for application, cv, dist in result.all()]

    async def _fulltext_candidates(
        self,
        db: AsyncSession,
        job: Job,
        limit: int | None = None,
    ) -> list[tuple]:
        """Find candidates by full-text relevance over their CV text."""
        job_description = job.description if isinstance(job.description, dict) else {}
        query_text = build_job_embedding_text(job_description)
        if not query_text.strip():
            return []

        ts_query = func.websearch_to_tsquery("english", query_text)
        stmt = (
            select(
                JobApplication,
                CandidateCV,
                func.ts_rank(CandidateCV.search_vector, ts_query).label("relevance"),
            )
            .join(CandidateCV, JobApplication.cv_id == CandidateCV.id)
            .where(
                JobApplication.job_id == job.id,
                JobApplication.status.in_(["applied"]),
                CandidateCV.embedding.isnot(None),
                CandidateCV.search_vector.isnot(None),
                CandidateCV.search_vector.op("@@")(ts_query),
            )
            .order_by(func.ts_rank(CandidateCV.search_vector, ts_query).desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return [(application, cv, None) for application, cv, _ in result.all()]

    async def _hybrid_retrieve(
        self,
        db: AsyncSession,
        job: Job,
        limit: int | None = None,
    ) -> list[tuple]:
        """Run semantic and full-text search, then merge results with RRF.

        Both queries run sequentially (not concurrently) because a single
        AsyncSession maps to one asyncpg connection. Returns tuples of
        (application, cv, semantic_distance, rrf_score) ordered by RRF score,
        capped to `limit` when provided.
        """
        semantic = await self._semantic_candidates(db, job, limit)
        fulltext = await self._fulltext_candidates(db, job, limit)

        k = job.top_k or 50
        fused = reciprocal_rank_fusion([semantic, fulltext], k=k)

        normalized = [
            (application, cv, distance if distance is not None else 2.0, rrf_score)
            for application, cv, distance, rrf_score in fused
        ]
        if limit is not None:
            return normalized[:limit]
        return normalized

    async def screen_application(self, db: AsyncSession, job: Job) -> Optional[UUID]:
        run = AIScreeningRun(job_id=job.id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        logger.info(
            "AI screening run %s started for job %s (top_k=%s, rerank=%s, has_embedding=%s)",
            run.id, job.id, job.top_k, job.rerank, job.embedding is not None,
        )

        if job.embedding is None:
            msg = f"Job {job.id} has no embedding; cannot screen"
            logger.error(msg)
            run.status = "failed"
            run.error_message = msg
            run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
            return run.id

        try:
            fused = await self._hybrid_retrieve(db, job, limit=job.top_k or 50)
            logger.info("AI screening run %s: hybrid retrieval found %s candidate(s) for job %s", run.id, len(fused), job.id)

            if not fused:
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                run.candidates_screened = 0
                await db.commit()
                return run.id

            documents = []
            for application, cv, _, _ in fused:
                resume_json = cv.resume_text if cv.resume_text else {}
                resume_text = _format_cv_text(resume_json) if isinstance(resume_json, dict) else str(resume_json)
                documents.append(resume_text)

            job_desc_json = job.description if isinstance(job.description, dict) else {}
            job_desc_text = _format_job_description(job_desc_json)

            rerank_results = await self._rerank(
                query=job_desc_text,
                documents=documents,
                top_n=len(documents),
            )
            logger.info("AI screening run %s: rerank returned %s result(s)", run.id, len(rerank_results))

            rerank_scores = {
                r["index"]: r["relevance_score"]
                for r in rerank_results
            }

            for idx, (application, cv, _, rrf_score) in enumerate(fused):
                rerank_score = rerank_scores.get(idx, rrf_score)
                if rerank_score is None:
                    rerank_score = rrf_score
                resume_json = cv.resume_text if cv.resume_text else {}
                resume_text = cv.raw_text or (_format_cv_text(resume_json) if isinstance(resume_json, dict) else str(resume_json))
                result = await self._generate_feedback_with_retry(job_desc_text, resume_text)
                feedback = result.feedback
                logger.info(
                    "AI screening run %s: generated feedback for application %s (attempts=%s, passed=%s)",
                    run.id, application.id, len(result.attempts) or 1, result.passed,
                )
                screening = AIScreening(
                    job_application_id=application.id,
                    rerank_score=rerank_score,
                    rrf_score=rrf_score,
                    feedback=feedback,
                )
                db.add(screening)
                application.status = "screened"

            await db.commit()
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            run.candidates_screened = len(fused)
            await db.commit()
            logger.info(
                "AI screening run %s completed for job %s: %s candidate(s) screened",
                run.id, job.id, len(fused),
            )
            return run.id
        except Exception as e:
            logger.error("AI screening run %s failed for job %s: %s", run.id, job.id, e)
            logger.error(traceback.format_exc())
            try:
                run.status = "failed"
                run.error_message = str(e)[:1000]
                run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await db.commit()
            except Exception as inner:
                logger.error("Failed to record AI screening run %s failure: %s", run.id, inner)
            raise

ai_screening_service = AIScreeningService()
