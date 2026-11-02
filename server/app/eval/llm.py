"""DeepEval custom LLM judge backed by LiteLLM + OpenRouter.

The project's AI stack runs through LiteLLM routed to OpenRouter (see
`app.services.ai_screening_service`). DeepEval defaults to OpenAI directly,
so we wrap the same LiteLLM path in a `DeepEvalBaseLLM` subclass and use
`instructor` for JSON confinement so the judge always returns the Pydantic
schema DeepEval's metrics expect.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Type

import litellm
import instructor
from pydantic import BaseModel

from deepeval.models import DeepEvalBaseLLM

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Separate model for the *judge* (defaults to the same LLM_MODEL used for
# generation, but can be overridden via EVAL_LLM_MODEL to use a stronger
# model for evaluation without affecting the production screening model).
JUDGE_MODEL = getattr(settings, "EVAL_LLM_MODEL", None) or settings.LLM_MODEL


class LiteLLMJudge(DeepEvalBaseLLM):
    """DeepEval evaluation model that re-uses the project's LiteLLM/OpenRouter client."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self._model = model or JUDGE_MODEL
        self._api_key = api_key or settings.OPENROUTER_API_KEY
        self._temperature = temperature
        # `instructor` wraps litellm's async completion to enforce Pydantic schemas
        self._instructor_client = instructor.from_litellm(litellm.acompletion)

    def load_model(self):
        # Nothing to load — LiteLLM is a remote client. Returning self
        # satisfies the DeepEvalBaseLLM contract.
        return self

    def get_model_name(self) -> str:
        return f"litellm-openrouter:{self._model}"

    async def a_generate(
        self, prompt: str, schema: Optional[Type[BaseModel]] = None
    ) -> BaseModel | str:
        if schema is None:
            # Raw text generation — used by metrics that don't require JSON.
            response = await litellm.acompletion(
                model=f"openrouter/{self._model}",
                messages=[{"role": "user", "content": prompt}],
                api_key=self._api_key,
                temperature=self._temperature,
            )
            return response.choices[0].message.content or ""

        # Schema-constrained generation via instructor.
        try:
            return await self._instructor_client.chat.completions.create(
                model=f"openrouter/{self._model}",
                messages=[{"role": "user", "content": prompt}],
                api_key=self._api_key,
                temperature=self._temperature,
                response_model=schema,
                max_retries=2,
            )
        except Exception as e:
            logger.warning(
                "Instructor JSON confinement failed for %s, falling back to raw parse: %s",
                self._model, e,
            )
            return await self._raw_json_fallback(prompt, schema)

    def generate(
        self, prompt: str, schema: Optional[Type[BaseModel]] = None
    ) -> BaseModel | str:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already inside an event loop — run in a fresh loop
                # to avoid "Future attached to a different loop" errors.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run, self.a_generate(prompt, schema)
                    ).result()
        except RuntimeError:
            pass
        return asyncio.run(self.a_generate(prompt, schema))

    async def _raw_json_fallback(
        self, prompt: str, schema: Type[BaseModel]
    ) -> BaseModel:
        """Best-effort raw JSON parse if instructor fails."""
        response = await litellm.acompletion(
            model=f"openrouter/{self._model}",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        f"Return ONLY valid JSON matching this schema:\n"
                        f"{json.dumps(schema.model_json_schema())}"
                    ),
                }
            ],
            api_key=self._api_key,
            temperature=self._temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return schema(**json.loads(content.strip()))


# Singleton — reuse across metrics so we don't re-init instructor per call.
_default_judge: Optional[LiteLLMJudge] = None


def get_judge() -> LiteLLMJudge:
    """Return a cached LiteLLMJudge instance."""
    global _default_judge
    if _default_judge is None:
        _default_judge = LiteLLMJudge()
    return _default_judge
