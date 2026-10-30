"""Anthropic Claude adapter using forced tool calls for reliable structured output."""
import time

import anthropic

from ..config import Settings
from ..core.ports import LLMError


class AnthropicLLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self.models = {"interviewer": settings.interviewer_model, "evaluator": settings.evaluator_model}

    def structured(self, *, role, system, user, tool_name, tool_description, schema,
                   temperature=None, max_tokens=1200) -> dict:
        if self.client is None:
            raise LLMError("ANTHROPIC_API_KEY is not set. Add it to your .env file and restart the server.")
        kwargs = dict(
            model=self.models[role],
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{"name": tool_name, "description": tool_description, "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.client.messages.create(**kwargs)
                for block in resp.content:
                    if block.type == "tool_use" and block.name == tool_name:
                        return dict(block.input)
                raise LLMError("Model did not return the expected tool call")
            except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
            except anthropic.BadRequestError as e:
                if "temperature" in str(e) and "temperature" in kwargs:
                    kwargs.pop("temperature")  # some models don't accept it; retry without
                    last_err = e
                    continue
                raise LLMError(f"LLM request rejected: {e}") from e
            except anthropic.APIStatusError as e:
                raise LLMError(f"LLM error {e.status_code}: {e}") from e
        raise LLMError(f"LLM unavailable after retries: {last_err}")
