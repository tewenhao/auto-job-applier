"""Tests for the profile interview (LLM mocked — no network)."""

from __future__ import annotations

from typing import Any

from app.profile.interview import InterviewStep, next_step


class _FakeLLM:
    """Captures the messages sent, and returns a canned step."""

    def __init__(self, step: InterviewStep) -> None:
        self.step = step
        self.messages: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> InterviewStep:
        self.messages = kwargs["messages"]
        return self.step


def test_conversation_always_ends_with_a_user_turn() -> None:
    """The transcript ends on a question whenever the last one went unanswered
    (a reload, or asking to draft early). The API rejects a conversation that
    ends with an assistant turn, so a nudge is appended."""
    llm = _FakeLLM(InterviewStep(ready=True))
    transcript = [
        {"role": "assistant", "content": "What would you like to add?"},
        {"role": "user", "content": "A hackathon project."},
        {"role": "assistant", "content": "What problem did it solve?"},  # unanswered
    ]
    next_step(llm, transcript)  # type: ignore[arg-type]
    assert llm.messages[-1]["role"] == "user"
    assert "No answer" in llm.messages[-1]["content"]


def test_normal_turn_is_left_alone() -> None:
    llm = _FakeLLM(InterviewStep(question="And what was your part in it?"))
    transcript = [
        {"role": "assistant", "content": "What would you like to add?"},
        {"role": "user", "content": "A hackathon project."},
    ]
    next_step(llm, transcript)  # type: ignore[arg-type]
    assert llm.messages[-1]["content"] == "A hackathon project."


def test_no_question_and_not_ready_is_treated_as_ready() -> None:
    """A step with neither would stall the interview."""
    llm = _FakeLLM(InterviewStep(question=None, ready=False))
    step = next_step(llm, [{"role": "user", "content": "something"}])  # type: ignore[arg-type]
    assert step.ready is True


def test_opening_turn_needs_no_model_call() -> None:
    llm = _FakeLLM(InterviewStep(ready=True))
    step = next_step(llm, [])  # type: ignore[arg-type]
    assert step.question and not step.ready
    assert llm.messages == []  # nothing was sent
