"""Deterministic guardrails applied on top of the LLM's requested action."""
from dataclasses import dataclass
from datetime import datetime

from .enums import NextAction
from .models import RoundState, TurnDecision


@dataclass
class Enforced:
    action: NextAction
    overridden: bool
    reason: str | None = None


def enforce(rnd: RoundState, decision: TurnDecision, now: datetime) -> Enforced:
    requested = decision.next_action
    topic = rnd.current_topic

    def force(action: NextAction, reason: str) -> Enforced:
        if action == NextAction.NEXT_TOPIC and rnd.next_topic is None:
            action, reason = NextAction.END_ROUND, reason + "; no topics left"
        return Enforced(action, action != requested, reason)

    time_up = rnd.elapsed_sec(now) >= rnd.duration_min * 60
    if time_up:
        return force(NextAction.END_ROUND, "time budget reached")
    if rnd.candidate_turns >= rnd.max_candidate_turns:
        return force(NextAction.END_ROUND, "turn budget reached")
    if topic is None:
        return force(NextAction.END_ROUND, "no current topic")

    if requested in (NextAction.PROBE, NextAction.TWIST) and topic.probes >= rnd.max_probes:
        return force(NextAction.NEXT_TOPIC, "probe limit for topic reached")
    if requested == NextAction.HINT and topic.hints >= rnd.max_hints:
        return force(NextAction.NEXT_TOPIC, "hint limit for topic reached")
    if decision.answer_quality == "dont_know" and requested in (NextAction.PROBE, NextAction.TWIST):
        return force(NextAction.NEXT_TOPIC, "candidate said they don't know; respect it and move on")
    if requested == NextAction.NEXT_TOPIC and rnd.next_topic is None:
        return force(NextAction.END_ROUND, "all planned topics done")
    if requested == NextAction.END_ROUND and rnd.next_topic is not None:
        return force(NextAction.NEXT_TOPIC, "planned topics remain and time is left")
    return Enforced(requested, False)
