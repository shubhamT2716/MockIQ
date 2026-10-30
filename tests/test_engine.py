from app.adapters.llm_fake import FakeLLM
from app.core.enums import RoundStatus, SessionStatus, TopicStatus
from app.core.evaluation.report import build_report
from app.core.evaluation.scorer import score_round
from app.core.interview_engine import InterviewEngine


def test_full_session_runs_to_completion(state):
    engine = InterviewEngine(FakeLLM())
    engine.start(state)
    assert state.status == SessionStatus.LIVE and state.round.status == RoundStatus.QUESTIONING
    for _ in range(300):
        if state.status == SessionStatus.COMPLETED:
            break
        engine.handle_candidate_turn(state, "I would use a hash map to count frequencies then a heap.")
    assert state.status == SessionStatus.COMPLETED
    assert all(r.status == RoundStatus.COMPLETED for r in state.rounds)
    for r in state.rounds:
        assert all(t.status != TopicStatus.IN_PROGRESS for t in r.topics)
        assert all(t.probes <= r.max_probes for t in r.topics)
        assert r.candidate_turns <= r.max_candidate_turns


def test_no_question_is_restated_and_not_scored(state, packs):
    engine = InterviewEngine(FakeLLM())
    opening = engine.start(state).messages[0]["text"]
    assert "grid of 1s and 0s" in opening
    assert "islands" in opening
    engine.handle_candidate_turn(state, "can you explain the problem")
    engine.handle_candidate_turn(state, "there is no questions on this")
    said = [t.text for t in state.turns if t.speaker == "INTERVIEWER"]
    assert state.round.topic_index == 0
    assert all("(probe)" not in t and "(next_topic)" not in t for t in said)
    assert any("grid of 1s and 0s" in t for t in said[1:])
    scored = score_round(state, state.rounds[0], packs["backend-sde"], FakeLLM(), passes=1)
    assert scored.overall is None and scored.verdict is None
    assert all(c.score is None and not c.evidence for c in scored.competencies)
    report = build_report(state, [scored], FakeLLM())
    assert report["verdict"] is None
    assert "not a hire signal" in report["summary"]


def test_rules_override_triggers_regeneration(state):
    llm = FakeLLM(decision_cycle=("PROBE",))  # LLM always wants to probe
    engine = InterviewEngine(llm)
    engine.start(state)
    r = state.round
    for _ in range(r.max_probes + 1):
        engine.handle_candidate_turn(state, "Some answer about trees and graphs using BFS.")
    assert r.topic_index == 1  # forced to move on
    overridden = [t for t in state.turns if t.meta.get("overridden")]
    assert overridden and overridden[0].meta["action"] == "NEXT_TOPIC"


def test_end_early_marks_rounds(state):
    engine = InterviewEngine(FakeLLM())
    engine.start(state)
    engine.handle_candidate_turn(state, "My approach is DFS over the grid.")
    engine.end_early(state)
    assert state.status == SessionStatus.COMPLETED
    assert state.rounds[0].status == RoundStatus.ENDED_EARLY
    assert all(r.status == RoundStatus.SKIPPED for r in state.rounds[1:])


def test_skip_moves_on_and_records_skipped(state):
    from app.core.enums import TopicStatus
    llm = FakeLLM()
    engine = InterviewEngine(llm)
    engine.start(state)
    r = state.round
    first = r.current_topic
    res = engine.skip_question(state)
    assert first.status == TopicStatus.SKIPPED and r.topic_index == 1
    assert r.current_topic.status == TopicStatus.IN_PROGRESS
    assert state.turns[-2].meta == {"command": "skip"}
    assert res.events and res.events[0]["type"] == "topic_changed"
    # skipping the last topic wraps the round up instead
    r.topic_index = len(r.topics) - 1
    engine.skip_question(state)
    assert r.status == RoundStatus.WRAP_UP and r.topics[-1].status == TopicStatus.SKIPPED
    # "skip" during wrap-up closes the round like "no questions"
    engine.skip_question(state)
    assert r.status == RoundStatus.COMPLETED and state.current_round == 1
