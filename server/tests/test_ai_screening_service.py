import os
from types import SimpleNamespace

import pytest


os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "test")
os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("database_url", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("secret_key", "test-secret")
os.environ.setdefault("algorithm", "HS256")
os.environ.setdefault("access_token_expire_minutes", "30")
os.environ.setdefault("environment", "test")
os.environ.setdefault("debug", "false")

from app.services import ai_screening_service as module
from app.services.ai_screening_service import AIScreeningService
from app.models.ai_screening import AIScreening
import app.eval.judge as judge_module


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = f"id-{len(self.added)}"
        return obj


@pytest.fixture(autouse=True)
def setup_database():
    yield


@pytest.fixture(autouse=True)
def clean_database():
    yield


def _completion_response(content: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


@pytest.mark.asyncio
async def test_generate_feedback_parses_valid_json(monkeypatch):
    service = AIScreeningService()
    content = """
{
  "matched": ["Python"],
  "missing": ["AWS"],
  "strengths": ["Backend experience"],
  "concerns": ["No cloud work listed"],
  "interview_questions": ["Describe a production API you owned."],
  "recommendation": {
    "decision": "Proceed",
    "reason": "Strong backend match."
  }
}
"""

    async def fake_completion(**kwargs):
        return _completion_response(content)

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion)

    feedback = await service._generate_feedback("job", "resume")

    assert feedback["matched"] == ["Python"]
    assert feedback["missing"] == ["AWS"]
    assert feedback["recommendation"] == {
        "decision": "Proceed",
        "reason": "Strong backend match.",
    }


@pytest.mark.asyncio
async def test_generate_feedback_parses_fenced_json(monkeypatch):
    service = AIScreeningService()
    content = """```json
{
  "matched": [],
  "missing": [],
  "strengths": [],
  "concerns": [],
  "interview_questions": [],
  "recommendation": {
    "decision": "Reject",
    "reason": "Not enough role evidence."
  }
}
```"""

    async def fake_completion(**kwargs):
        return _completion_response(content)

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion)

    feedback = await service._generate_feedback("job", "resume")

    assert feedback["recommendation"]["decision"] == "Reject"
    assert feedback["recommendation"]["reason"] == "Not enough role evidence."


@pytest.mark.asyncio
async def test_generate_feedback_raises_on_invalid_json(monkeypatch):
    service = AIScreeningService()

    async def fake_completion(**kwargs):
        return _completion_response("not json")

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion)

    with pytest.raises(ValueError, match="AI feedback generation failed"):
        await service._generate_feedback("job", "resume")


def test_normalize_feedback_raises_on_unknown_decision():
    service = AIScreeningService()

    with pytest.raises(ValueError, match="decision must be Proceed or Reject"):
        service._normalize_feedback(
            {
                "matched": ["Python"],
                "recommendation": {
                    "decision": "Maybe",
                    "reason": "Ambiguous output.",
                },
            }
        )


def test_reciprocal_rank_fusion_merges_and_orders():
    app1 = SimpleNamespace(id="a")
    app2 = SimpleNamespace(id="b")
    app3 = SimpleNamespace(id="c")

    semantic = [(app1, None, 0.1), (app2, None, 0.2)]
    fulltext = [(app2, None, None), (app3, None, None)]

    fused = module.reciprocal_rank_fusion([semantic, fulltext], k=60)

    ids = [item[0].id for item in fused]
    assert ids == ["b", "a", "c"]

    scores = {item[0].id: item[3] for item in fused}
    assert scores["b"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["c"] == pytest.approx(1 / 62)


def test_reciprocal_rank_fusion_appends_rrf_score():
    app1 = SimpleNamespace(id="a")
    app2 = SimpleNamespace(id="b")

    fused = module.reciprocal_rank_fusion(
        [[(app1, None, 0.1)], [(app2, None, None)]],
        k=60,
    )

    assert len(fused) == 2
    for item in fused:
        assert len(item) == 4
        assert isinstance(item[3], float)


@pytest.mark.asyncio
async def test_hybrid_retrieve_uses_job_top_k_as_rrf_k(monkeypatch):
    service = AIScreeningService()
    job = SimpleNamespace(
        id="job1",
        top_k=12,
        description={"requirements": ["Laravel"], "jobdesk": []},
    )

    captured = {}

    async def fake_semantic(db, job, limit=None):
        return [("semantic",)]

    async def fake_fulltext(db, job, limit=None):
        return []

    def fake_rrf(lists, k=60):
        captured["k"] = k
        return []

    monkeypatch.setattr(service, "_semantic_candidates", fake_semantic)
    monkeypatch.setattr(service, "_fulltext_candidates", fake_fulltext)
    monkeypatch.setattr(module, "reciprocal_rank_fusion", fake_rrf)

    await service._hybrid_retrieve(None, job, limit=12)

    assert captured["k"] == 12


@pytest.mark.asyncio
async def test_screen_application_screens_all_top_k_with_rrf_and_rerank(monkeypatch):
    service = AIScreeningService()

    app1 = SimpleNamespace(id="a1", status="applied")
    app2 = SimpleNamespace(id="a2", status="applied")
    cv1 = SimpleNamespace(resume_text={"candidate_summary": "X"}, raw_text="raw X")
    cv2 = SimpleNamespace(resume_text={"candidate_summary": "Y"}, raw_text="raw Y")
    job = SimpleNamespace(
        id="job1",
        top_k=2,
        rerank=1,
        embedding=[0.1, 0.2],
        description={"requirements": ["Laravel"], "jobdesk": []},
    )

    fused = [
        (app1, cv1, 0.1, 0.0333),
        (app2, cv2, 0.2, 0.0166),
    ]

    async def fake_hybrid(db, job, limit=None):
        return fused

    async def fake_rerank(query, documents, top_n):
        assert top_n == len(documents)
        return [{"index": 0, "relevance_score": 0.9}]

    async def fake_feedback(job_desc_text, resume_text, critique=None):
        return {"recommendation": {"decision": "Proceed", "reason": "ok"}}

    async def fake_feedback_with_retry(job_desc_text, resume_text):
        feedback = await fake_feedback(job_desc_text, resume_text)
        return module.FeedbackResult(feedback=feedback, passed=True, total_tokens=10)

    monkeypatch.setattr(service, "_hybrid_retrieve", fake_hybrid)
    monkeypatch.setattr(service, "_rerank", fake_rerank)
    monkeypatch.setattr(service, "_generate_feedback_with_retry", fake_feedback_with_retry)

    db = FakeDB()
    run_id = await service.screen_application(db, job)

    assert run_id is not None

    screenings = [o for o in db.added if isinstance(o, AIScreening)]
    assert len(screenings) == 2

    for s in screenings:
        assert s.rrf_score is not None
        assert s.rerank_score is not None
        assert not hasattr(s, "top_k_score")

    assert app1.status == "screened"
    assert app2.status == "screened"

    by_app = {s.job_application_id: s for s in screenings}
    assert by_app["a1"].rerank_score == pytest.approx(0.9)
    assert by_app["a1"].rrf_score == pytest.approx(0.0333)
    assert by_app["a2"].rerank_score == pytest.approx(0.0166)
    assert by_app["a2"].rrf_score == pytest.approx(0.0166)


# ---- Generate -> judge -> retry loop --------------------------------------


def _valid_feedback() -> dict:
    return {
        "matched": ["Python"],
        "missing": ["AWS"],
        "strengths": ["Backend experience"],
        "concerns": [],
        "interview_questions": ["Describe a production API you owned."],
        "recommendation": {"decision": "Proceed", "reason": "Strong backend match."},
    }


def _verdict(score: int) -> "object":
    from app.eval.judge import JudgeVerdict

    return JudgeVerdict(
        score=score,
        dimension_scores={
            "completeness": score,
            "relevance": score,
            "specificity": score,
            "actionability": score,
            "groundedness": score,
        },
        strengths=["Correct definition"],
        weaknesses=["Missing example"],
        recommendations=["Add a real-world example"],
        regeneration_instructions="Add a concrete project example.",
    )


@pytest.mark.asyncio
async def test_generate_feedback_injects_critique(monkeypatch):
    service = AIScreeningService()
    captured = {}

    async def fake_completion(**kwargs):
        captured["prompt"] = kwargs["messages"][0]["content"]
        return _completion_response(
            '{"matched": [], "missing": [], "strengths": [], "concerns": [], '
            '"interview_questions": [], "recommendation": {"decision": "Reject", '
            '"reason": "Not enough role evidence."}}'
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion)

    await service._generate_feedback("job", "resume", critique="ADD THIS CRITIQUE")

    assert "ADD THIS CRITIQUE" in captured["prompt"]


@pytest.mark.asyncio
async def test_retry_loop_returns_on_pass(monkeypatch):
    service = AIScreeningService()
    calls = []

    async def fake_generate(job, resume, critique=None):
        calls.append(critique)
        return _valid_feedback()

    async def fake_judge(job, resume, feedback):
        return _verdict(9)

    monkeypatch.setattr(service, "_generate_feedback", fake_generate)
    monkeypatch.setattr(judge_module, "score_feedback", fake_judge)
    monkeypatch.setattr(module.settings, "EVAL_RETRY_MAX", 3)
    monkeypatch.setattr(module.settings, "EVAL_RETRY_THRESHOLD", 8.0)

    result = await service._generate_feedback_with_retry("job", "resume")

    assert result.passed is True
    assert len(result.attempts) == 1
    assert result.best_attempt == 1
    assert result.attempts[0].judge_score == 9


@pytest.mark.asyncio
async def test_retry_loop_structural_fail_skips_judge(monkeypatch):
    service = AIScreeningService()

    def incomplete():
        feedback = _valid_feedback()
        feedback["interview_questions"] = []
        return feedback

    async def fake_generate(job, resume, critique=None):
        return incomplete()

    def fake_judge(job, resume, feedback):
        raise AssertionError("judge must not run when structural gate fails")

    monkeypatch.setattr(service, "_generate_feedback", fake_generate)
    monkeypatch.setattr(judge_module, "score_feedback", fake_judge)
    monkeypatch.setattr(module.settings, "EVAL_RETRY_MAX", 3)

    result = await service._generate_feedback_with_retry("job", "resume")

    assert result.passed is False
    assert len(result.attempts) == 4
    for attempt in result.attempts:
        assert attempt.structural_passed is False
        assert attempt.judge_score is None
        assert attempt.judge_verdict is None
        assert "output_completeness" in attempt.structural_failures
    assert result.best_attempt == 4


@pytest.mark.asyncio
async def test_retry_loop_returns_best_so_far(monkeypatch):
    service = AIScreeningService()
    scores = iter([6, 7, 5, 7])
    critiques = []

    async def fake_generate(job, resume, critique=None):
        critiques.append(critique)
        return _valid_feedback()

    async def fake_judge(job, resume, feedback):
        return _verdict(next(scores))

    monkeypatch.setattr(service, "_generate_feedback", fake_generate)
    monkeypatch.setattr(judge_module, "score_feedback", fake_judge)
    monkeypatch.setattr(module.settings, "EVAL_RETRY_MAX", 3)
    monkeypatch.setattr(module.settings, "EVAL_RETRY_THRESHOLD", 8.0)

    result = await service._generate_feedback_with_retry("job", "resume")

    assert result.passed is False
    assert len(result.attempts) == 4
    assert result.best_attempt == 2
    assert [a.judge_score for a in result.attempts] == [6, 7, 5, 7]
    assert critiques[0] is None
    assert all(c is not None for c in critiques[1:])


