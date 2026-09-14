import os
import json
import logging
import time
from typing import TypeVar, Type, Any, Dict, List
from pydantic import BaseModel
import groq
from agent.llm.provider import LLMProvider, T

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing")
        self.client = groq.AsyncGroq(api_key=api_key)
        self.model = os.getenv("LLM_MODEL")
        if not self.model:
            raise ValueError("LLM_MODEL is missing in configuration. Agent must explicitly declare which model to use.")
        
    async def generate_structured(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        response_model: Type[T]
    ) -> T:
        # Convert Pydantic model to JSON schema for the prompt
        schema = response_model.model_json_schema()
        
        # We append a strong instruction to return JSON matching the schema
        augmented_system = (
            f"{system_prompt}\n\n"
            f"You MUST return ONLY valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            f"Do not include markdown blocks or any other text outside the JSON."
        )
        
        formatted_messages = [{"role": "system", "content": augmented_system}]
        formatted_messages.extend(messages)

        # RT-B0: this is a raw client call, not an SDK stt/tts plugin, so
        # there's no metrics_collected event to wire up -- duration has to
        # be measured here explicitly.
        start = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=formatted_messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        duration_ms = (time.perf_counter() - start) * 1000
        usage = response.usage
        logger.info(
            "[LLM-METRICS] model=%s duration_ms=%.1f prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            self.model, duration_ms,
            getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None),
            getattr(usage, "total_tokens", None),
        )

        content = response.choices[0].message.content
        # Parse the JSON into the Pydantic model
        return response_model.model_validate_json(content)

    async def generate_text(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]]
    ) -> str:
        formatted_messages = [{"role": "system", "content": system_prompt}]
        formatted_messages.extend(messages)

        start = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=formatted_messages,
            temperature=0.7,
        )
        duration_ms = (time.perf_counter() - start) * 1000
        usage = response.usage
        logger.info(
            "[LLM-METRICS] model=%s duration_ms=%.1f prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            self.model, duration_ms,
            getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None),
            getattr(usage, "total_tokens", None),
        )

        return response.choices[0].message.content or ""
