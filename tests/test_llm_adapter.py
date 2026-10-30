from types import SimpleNamespace

import pytest

from app.adapters.llm_anthropic import AnthropicLLM
from app.config import Settings
from app.core.ports import LLMError


def test_returns_forced_tool_input():
    llm = AnthropicLLM(Settings(anthropic_api_key="test-key"))
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="hi"),
                                        SimpleNamespace(type="tool_use", name="say", input={"utterance": "Hello"})])

    llm.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    out = llm.structured(role="interviewer", system="s", user="u", tool_name="say",
                         tool_description="d", schema={"type": "object"}, temperature=0.5)
    assert out == {"utterance": "Hello"}
    assert seen["tool_choice"] == {"type": "tool", "name": "say"}
    assert seen["model"] == Settings().interviewer_model


def test_missing_key_gives_clear_error():
    llm = AnthropicLLM(Settings(anthropic_api_key=None))
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        llm.structured(role="evaluator", system="s", user="u", tool_name="t",
                       tool_description="d", schema={"type": "object"})
