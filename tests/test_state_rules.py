import pytest

from app.core.enums import NextAction, RoundStatus
from app.core.models import TurnDecision, utcnow
from app.core.rules_engine import enforce
from app.core.state_machine import InvalidTransition, state_for_action, transition


def decision(action, quality="partial"):
    return TurnDecision(answer_quality=quality, estimated_depth=2, next_action=action, utterance="x")


def live_round(state):
    r = state.rounds[0]
    r.status = RoundStatus.QUESTIONING
    r.started_at = utcnow()
    return r


def test_state_machine_blocks_illegal_moves():
    assert state_for_action(RoundStatus.QUESTIONING, NextAction.PROBE) == RoundStatus.PROBING
    assert state_for_action(RoundStatus.PROBING, NextAction.CLARIFY) == RoundStatus.PROBING
    with pytest.raises(InvalidTransition):
        transition(RoundStatus.COMPLETED, RoundStatus.QUESTIONING)
    with pytest.raises(InvalidTransition):
        transition(RoundStatus.PLANNED, RoundStatus.WRAP_UP)


def test_probe_limit_forces_next_topic(state):
    r = live_round(state)
    r.current_topic.probes = r.max_probes
    e = enforce(r, decision(NextAction.PROBE), utcnow())
    assert e.action == NextAction.NEXT_TOPIC and e.overridden


def test_hint_limit(state):
    r = live_round(state)
    r.current_topic.hints = r.max_hints
    assert enforce(r, decision(NextAction.HINT), utcnow()).action == NextAction.NEXT_TOPIC


def test_time_up_ends_round(state, later):
    r = live_round(state)
    assert enforce(r, decision(NextAction.PROBE), later(r.duration_min + 1)).action == NextAction.END_ROUND


def test_premature_end_round_blocked(state):
    r = live_round(state)
    assert enforce(r, decision(NextAction.END_ROUND), utcnow()).action == NextAction.NEXT_TOPIC


def test_next_topic_on_last_topic_becomes_end_round(state):
    r = live_round(state)
    r.topic_index = len(r.topics) - 1
    e = enforce(r, decision(NextAction.NEXT_TOPIC), utcnow())
    assert e.action == NextAction.END_ROUND


def test_dont_know_is_respected(state):
    r = live_round(state)
    assert enforce(r, decision(NextAction.PROBE, "dont_know"), utcnow()).action == NextAction.NEXT_TOPIC


def test_turn_budget(state):
    r = live_round(state)
    r.candidate_turns = r.max_candidate_turns
    assert enforce(r, decision(NextAction.PROBE), utcnow()).action == NextAction.END_ROUND
