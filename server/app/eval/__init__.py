"""Evaluation package for the AI screening service.

Production modules (run at runtime):

    evaluators.py            Rule-based, deterministic checks on the screening
                             feedback dict (schema compliance, decision validity,
                             required fields, output completeness) plus latency /
                             token / cost metrics. No LLM involved. This is the
                             structural gate of the retry loop.
    judge.py                 LLM quality judge (0-10) that runs only when the
                             structural gate passes, returning strengths /
                             weaknesses / recommendations for the retry prompt.
                             Fidelity vs. the CV is checked via the `groundedness`
                             dimension (incl. internal-contradiction detection).
    mlflow_tracker.py        Logs one combined run per candidate (structural
                             metrics + judge metrics + judge_verdict.json
                             artifact) to MLflow when tracking is enabled.
    llm.py                   DeepEval judge backed by LiteLLM + OpenRouter,
                             re-using the project's existing client. Used by the
                             quality judge.
"""