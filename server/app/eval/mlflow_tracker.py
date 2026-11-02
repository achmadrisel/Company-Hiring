from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

import mlflow
from mlflow import MlflowClient

from app.core.config import get_settings
from app.eval.evaluators import ScreeningEvalResults, run_all_evaluators

logger = logging.getLogger(__name__)

settings = get_settings()


class MLflowTracker:
    def __init__(self) -> None:
        self._enabled = settings.MLFLOW_TRACKING_ENABLED
        if self._enabled:
            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            self._ensure_experiment()
            logger.info(
                "MLflow tracking enabled — uri=%s experiment=%s",
                settings.MLFLOW_TRACKING_URI,
                settings.MLFLOW_EXPERIMENT_NAME,
            )

    def _ensure_experiment(self) -> None:
        client = MlflowClient()
        exp = client.get_experiment_by_name(settings.MLFLOW_EXPERIMENT_NAME)
        if exp is not None and exp.lifecycle_stage == "active":
            if exp.artifact_location and not exp.artifact_location.startswith("/"):
                mlflow.set_experiment(experiment_id=exp.experiment_id)
                return
            logger.info(
                "Recreating experiment '%s' — old artifact location is local filesystem (%s)",
                settings.MLFLOW_EXPERIMENT_NAME,
                exp.artifact_location,
            )
            client.rename_experiment(
                exp.experiment_id,
                f"{settings.MLFLOW_EXPERIMENT_NAME}-old-{exp.experiment_id}",
            )
        exp_id = client.create_experiment(
            settings.MLFLOW_EXPERIMENT_NAME,
            artifact_location=self._artifact_root(),
        )
        mlflow.set_experiment(experiment_id=exp_id)

    @staticmethod
    def _artifact_root() -> str:
        uri = settings.MLFLOW_TRACKING_URI.rstrip("/")
        return f"{uri}/api/2.0/mlflow-artifacts/artifacts"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def log_screening(
        self,
        job_id: UUID,
        application_id: UUID,
        candidate_id: Optional[UUID],
        feedback: Dict[str, Any],
        eval_results: ScreeningEvalResults,
        model: str = "",
        run_id: Optional[UUID] = None,
        judge=None,
        attempts: Optional[list] = None,
        best_attempt_index: Optional[int] = None,
        passed: Optional[bool] = None,
        total_latency_ms: float = 0.0,
        total_tokens: int = 0,
        judge_model: str = "",
    ) -> None:
        if not self._enabled:
            return

        metrics = eval_results.all_metrics()
        params = {
            "job_id": str(job_id),
            "application_id": str(application_id),
            "candidate_id": str(candidate_id) if candidate_id else "",
            "model": model or settings.LLM_MODEL,
            "environment": settings.environment,
            "decision": feedback.get("recommendation", {}).get("decision", "unknown"),
        }
        if judge_model:
            params["judge_model"] = judge_model
        tags = {
            "mlflow.runName": f"screening_{application_id}",
            "decision": params["decision"],
            "environment": settings.environment,
            "job_id": str(job_id),
        }

        # Judge metrics are only present when the LLM judge ran (structural gate
        # passed). On structural failure they stay missing, per the eval contract.
        if judge is not None:
            metrics["judge_score"] = float(judge.score)
            metrics["judge_passed"] = 1.0 if passed else 0.0
        metrics["retry_attempts"] = float(len(attempts)) if attempts else 1.0
        if total_tokens:
            metrics["total_tokens"] = float(total_tokens)
        if total_latency_ms:
            metrics["total_latency_ms"] = float(total_latency_ms)

        try:
            with mlflow.start_run(tags=tags) as active_run:
                try:
                    mlflow.log_params(params)
                    mlflow.log_metrics(metrics)
                    if run_id:
                        mlflow.log_param("screening_run_id", str(run_id))
                    if judge is not None or attempts:
                        mlflow.log_dict(
                            dictionary=self._build_judge_artifact(
                                attempts=attempts,
                                best_attempt_index=best_attempt_index,
                                passed=passed,
                                judge=judge,
                            ),
                            artifact_file="judge_verdict.json",
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to log MLflow data for application %s: %s",
                        application_id, e,
                    )
                logger.info(
                    "Logged MLflow run %s for application %s (decision=%s, latency=%.0fms)",
                    active_run.info.run_id,
                    application_id,
                    params["decision"],
                    eval_results.latency_ms,
                )
        except Exception as e:
            logger.warning("Failed to log MLflow run for application %s: %s", application_id, e)

    @staticmethod
    def _build_judge_artifact(attempts, best_attempt_index, passed, judge) -> dict:
        attempt_rows = []
        if attempts:
            for a in attempts:
                attempt_rows.append({
                    "attempt": a.attempt,
                    "structural_passed": a.structural_passed,
                    "structural_failures": a.structural_failures,
                    "judge_score": a.judge_score,
                    "passed": a.passed,
                    "verdict": a.judge_verdict.model_dump() if a.judge_verdict is not None else None,
                })
        return {
            "attempts": attempt_rows,
            "best_attempt": (best_attempt_index + 1) if best_attempt_index is not None else None,
            "accepted": bool(passed),
            "final_verdict": judge.model_dump() if judge is not None else None,
        }

    @staticmethod
    def build_eval_results(
        feedback: dict,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> ScreeningEvalResults:
        return run_all_evaluators(
            feedback=feedback,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )


_tracker_instance: Optional[MLflowTracker] = None


def get_tracker() -> MLflowTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = MLflowTracker()
    return _tracker_instance
