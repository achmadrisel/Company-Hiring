from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.eval.mlflow_tracker import MLflowTracker, get_tracker
from app.models import Job
from app.models.ai_screening import AIScreening
from app.models.ai_screening_run import AIScreeningRun
from app.services.ai_screening_service import (
    AIScreeningService,
    FeedbackResult,
    _format_cv_text,
    _format_job_description,
)

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


class AIScreeningMLFlowService:
    def __init__(
        self,
        tracker: Optional[MLflowTracker] = None,
    ) -> None:
        self._inner = AIScreeningService()
        self._tracker = tracker or get_tracker()

    async def screen_application(self, db: AsyncSession, job: Job) -> Optional[UUID]:
        run = AIScreeningRun(job_id=job.id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        logger.info(
            "AI screening run %s started for job %s (top_k=%s, rerank=%s, has_embedding=%s, tracking=%s)",
            run.id, job.id, job.top_k, job.rerank, job.embedding is not None, self._tracker.enabled,
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
            fused = await self._inner._hybrid_retrieve(db, job, limit=None)
            logger.info("AI screening run %s: hybrid retrieval found %s candidate(s) for job %s", run.id, len(fused), job.id)

            if not fused:
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                run.candidates_screened = 0
                await db.commit()
                return run.id

            documents = []
            application_map = []
            for application, cv, dist, rrf_score in fused:
                resume_json = cv.resume_text if cv.resume_text else {}
                resume_text = _format_cv_text(resume_json) if isinstance(resume_json, dict) else str(resume_json)
                documents.append(resume_text)
                application_map.append((application, cv, float(dist), rrf_score))

            job_desc_json = job.description if isinstance(job.description, dict) else {}
            job_desc_text = _format_job_description(job_desc_json)

            rerank_results = await self._inner._rerank(
                query=job_desc_text,
                documents=documents,
                top_n=len(documents),
            )
            logger.info("AI screening run %s: rerank returned %s result(s)", run.id, len(rerank_results))

            rerank_scores = {}
            for r in rerank_results:
                rerank_scores[r["index"]] = r["relevance_score"]

            captor: dict = {}

            def on_feedback(feedback, response):
                captor["feedback"] = feedback
                captor["input_tokens"], captor["output_tokens"] = _extract_usage(response)

            self._inner._on_feedback_callback = on_feedback

            for idx, (application, cv, _, rrf_score) in enumerate(application_map):
                rerank_score = rerank_scores.get(idx, rrf_score)
                if rerank_score is None:
                    rerank_score = rrf_score
                resume_json = cv.resume_text if cv.resume_text else {}
                resume_text = cv.raw_text or (_format_cv_text(resume_json) if isinstance(resume_json, dict) else str(resume_json))

                captor.clear()

                result: FeedbackResult = await self._inner._generate_feedback_with_retry(job_desc_text, resume_text)
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

                if self._tracker.enabled:
                    if result.attempts and result.best_attempt:
                        final_idx = result.best_attempt - 1
                        final_attempt = result.attempts[final_idx]
                        input_tokens = final_attempt.input_tokens
                        output_tokens = final_attempt.output_tokens
                        elapsed_ms = final_attempt.latency_ms
                        judge_verdict = final_attempt.judge_verdict
                        best_attempt_index = final_idx
                    else:
                        input_tokens = captor.get("input_tokens", 0)
                        output_tokens = captor.get("output_tokens", 0)
                        elapsed_ms = result.total_latency_ms
                        judge_verdict = None
                        best_attempt_index = None

                    eval_results = self._tracker.build_eval_results(
                        feedback=feedback,
                        model=settings.LLM_MODEL,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=elapsed_ms,
                    )
                    self._tracker.log_screening(
                        job_id=job.id,
                        application_id=application.id,
                        candidate_id=cv.candidate_id,
                        feedback=feedback,
                        eval_results=eval_results,
                        model=settings.LLM_MODEL,
                        run_id=run.id,
                        judge=judge_verdict,
                        attempts=result.attempts,
                        best_attempt_index=best_attempt_index,
                        passed=result.passed,
                        total_latency_ms=result.total_latency_ms,
                        total_tokens=result.total_tokens,
                        judge_model=result.judge_model,
                    )

            self._inner._on_feedback_callback = None

            await db.commit()
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            run.candidates_screened = len(application_map)
            await db.commit()
            logger.info(
                "AI screening run %s completed for job %s: %s candidate(s) screened",
                run.id, job.id, len(application_map),
            )
            return run.id
        except Exception as e:
            logger.error("AI screening run %s failed for job %s: %s", run.id, job.id, e)
            import traceback
            logger.error(traceback.format_exc())
            self._inner._on_feedback_callback = None
            try:
                run.status = "failed"
                run.error_message = str(e)[:1000]
                run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await db.commit()
            except Exception as inner:
                logger.error("Failed to record AI screening run %s failure: %s", run.id, inner)
            raise
