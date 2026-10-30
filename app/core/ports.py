"""Interfaces the core depends on. Implementations live in app/adapters."""
from typing import Literal, Protocol


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def structured(
        self,
        *,
        role: Literal["interviewer", "evaluator"],
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        schema: dict,
        temperature: float | None = None,
        max_tokens: int = 1200,
    ) -> dict:
        """Return a dict that matches `schema` (forced tool call)."""
        ...
