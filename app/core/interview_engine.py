"""Turn controller: drives a session one candidate turn at a time."""
from dataclasses import dataclass, field
from datetime import datetime

from . import prompts
from .enums import LIVE_ROUND_STATES, NextAction, RoundStatus, SessionStatus, TopicStatus
from .models import TURN_DECISION_SCHEMA, RoundState, SessionState, TurnDecision, utcnow
from .ports import LLMClient, LLMError
from .rules_engine import enforce
from .state_machine import state_for_action, transition

UTTERANCE_SCHEMA = {
    "type": "object",
    "properties": {"utterance": {"type": "string"}},
    "required": ["utterance"],
}


class SessionNotLive(Exception):
    pass


@dataclass
class TurnResult:
    messages: list[dict] = field(default_factory=list)  # {"text", "round_seq"}
    events: list[dict] = field(default_factory=list)


class InterviewEngine:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    # ---------- public API ----------
    def start(self, state: SessionState, now: datetime | None = None) -> TurnResult:
        now = now or utcnow()
        if state.status != SessionStatus.PLANNED:
            raise SessionNotLive("Session already started")
        state.status = SessionStatus.LIVE
        result = TurnResult()
        self._start_round(state, now, result, is_first=True)
        return result

    def handle_candidate_turn(self, state: SessionState, text: str, code: str | None = None,
                              now: datetime | None = None) -> TurnResult:
        now = now or utcnow()
        if state.status != SessionStatus.LIVE:
            raise SessionNotLive("Session is not live")
        rnd = state.round
        result = TurnResult()
        text = text.strip()[:6000]

        if rnd.status == RoundStatus.WRAP_UP:
            state.add_turn("CANDIDATE", text, code=code)
            self._close_round(state, rnd, now, result)
            return result

        rnd.candidate_turns += 1
        state.add_turn("CANDIDATE", text, code=code)
        topic = rnd.current_topic

        decision = self._decide(state, rnd, now)
        self._apply_coverage(rnd, decision)
        enforced = enforce(rnd, decision, now)
        if enforced.overridden:
            decision = self._decide(state, rnd, now, forced=(enforced.action.value, enforced.reason))
        self._apply_action(state, rnd, topic, decision, enforced.action, result,
                           overridden=enforced.overridden, reason=enforced.reason)
        return result

    def skip_question(self, state: SessionState, code: str | None = None,
                      now: datetime | None = None) -> TurnResult:
        """Candidate said 'skip this one'. Deterministic: move on, and record the topic as skipped."""
        now = now or utcnow()
        if state.status != SessionStatus.LIVE:
            raise SessionNotLive("Session is not live")
        rnd = state.round
        if rnd.status == RoundStatus.WRAP_UP:  # "skip" while asked for questions = no questions
            return self.handle_candidate_turn(state, "No questions from me, thanks.", code, now)
        result = TurnResult()
        rnd.candidate_turns += 1
        state.add_turn("CANDIDATE", "(Asked to skip this question.)", code=code, meta={"command": "skip"})
        topic = rnd.current_topic
        time_up = rnd.elapsed_sec(now) >= rnd.duration_min * 60
        action = NextAction.NEXT_TOPIC if (rnd.next_topic and not time_up) else NextAction.END_ROUND
        reason = "the candidate asked to skip this question; acknowledge kindly in a few words, no judgment"
        decision = self._decide(state, rnd, now, forced=(action.value, reason))
        if topic:
            topic.status = TopicStatus.SKIPPED
        self._apply_action(state, rnd, topic, decision, action, result, overridden=False,
                           reason="candidate skipped", already_closed=True)
        return result

    def _apply_action(self, state: SessionState, rnd: RoundState, topic, decision: TurnDecision,
                      action: NextAction, result: TurnResult, *, overridden: bool, reason: str | None,
                      already_closed: bool = False) -> None:
        if action in (NextAction.PROBE, NextAction.TWIST):
            topic.probes += 1
        elif action == NextAction.HINT:
            topic.hints += 1
        elif action == NextAction.NEXT_TOPIC:
            if not already_closed:
                topic.close()
            rnd.topic_index += 1
            rnd.current_topic.status = TopicStatus.IN_PROGRESS
        elif action == NextAction.END_ROUND:
            self._finish_topics(rnd)

        rnd.status = state_for_action(rnd.status, action)
        state.add_turn("INTERVIEWER", decision.utterance, meta={
            "type": "question",
            "topic": topic.name if topic else None,
            "answer_quality": decision.answer_quality,
            "estimated_depth": decision.estimated_depth,
            "requested_action": decision.next_action.value,
            "action": action.value,
            "overridden": overridden,
            "override_reason": reason,
        })
        result.messages.append({"text": decision.utterance, "round_seq": rnd.seq})
        if action == NextAction.NEXT_TOPIC:
            result.events.append({"type": "topic_changed", "topic": rnd.current_topic.name})
        if action == NextAction.END_ROUND:
            result.events.append({"type": "round_wrap_up", "round_seq": rnd.seq})

    def end_early(self, state: SessionState, now: datetime | None = None) -> TurnResult:
        now = now or utcnow()
        result = TurnResult()
        if state.status == SessionStatus.COMPLETED:
            return result
        for r in state.rounds:
            if r.status in LIVE_ROUND_STATES:
                self._finish_topics(r)
                r.status = transition(r.status, RoundStatus.ENDED_EARLY)
                r.ended_at = now
            elif r.status == RoundStatus.PLANNED:
                r.status = transition(r.status, RoundStatus.SKIPPED)
        state.status = SessionStatus.COMPLETED
        result.events.append({"type": "session_completed", "early": True})
        return result

    # ---------- internals ----------
    def _say(self, state: SessionState, user: str) -> str:
        out = self.llm.structured(
            role="interviewer", system=prompts.interviewer_system(state), user=user,
            tool_name="say", tool_description="What the interviewer says out loud.",
            schema=UTTERANCE_SCHEMA, temperature=0.6, max_tokens=400,
        )
        return str(out.get("utterance", "")).strip() or "Let's continue."

    def _decide(self, state: SessionState, rnd: RoundState, now: datetime,
                forced: tuple[str, str] | None = None) -> TurnDecision:
        user = prompts.decision_prompt(state, rnd, now, forced)
        last_err = None
        for _ in range(2):
            try:
                raw = self.llm.structured(
                    role="interviewer", system=prompts.interviewer_system(state), user=user,
                    tool_name="turn_decision",
                    tool_description="Assess the latest answer and decide the interviewer's next move.",
                    schema=TURN_DECISION_SCHEMA, temperature=0.5, max_tokens=700,
                )
                return TurnDecision.model_validate(raw)
            except (LLMError, ValueError) as e:  # pydantic ValidationError is a ValueError
                last_err = e
        raise LLMError(f"Interviewer failed to decide: {last_err}")

    def _apply_coverage(self, rnd: RoundState, d: TurnDecision) -> None:
        topic = rnd.current_topic
        if topic is None or d.answer_quality in ("unclear", "off_topic"):
            return
        topic.depth_reached = max(topic.depth_reached, d.estimated_depth)
        for p in d.key_points_hit:
            if p not in topic.key_points_hit:
                topic.key_points_hit.append(p)
        topic.key_points_missed = [p for p in dict.fromkeys(topic.key_points_missed + d.key_points_missed)
                                   if p not in topic.key_points_hit][:12]

    def _finish_topics(self, rnd: RoundState) -> None:
        cur = rnd.current_topic
        if cur and cur.status == TopicStatus.IN_PROGRESS:
            cur.close()
        for t in rnd.topics[rnd.topic_index + 1:]:
            if t.status == TopicStatus.NOT_STARTED:
                t.status = TopicStatus.NOT_REACHED

    def _start_round(self, state: SessionState, now: datetime, result: TurnResult, is_first: bool) -> None:
        rnd = state.round
        rnd.status = transition(rnd.status, RoundStatus.QUESTIONING)
        rnd.started_at = now
        if rnd.current_topic:
            rnd.current_topic.status = TopicStatus.IN_PROGRESS
        text = self._say(state, prompts.opening_prompt(state, rnd, is_first))
        state.add_turn("INTERVIEWER", text, meta={"type": "opening", "topic": rnd.current_topic.name if rnd.current_topic else None})
        result.messages.append({"text": text, "round_seq": rnd.seq})
        result.events.append({"type": "round_started", "round_seq": rnd.seq, "title": rnd.title,
                              "round_type": rnd.type.value, "tools": rnd.tools, "duration_min": rnd.duration_min})

    def _close_round(self, state: SessionState, rnd: RoundState, now: datetime, result: TurnResult) -> None:
        has_next = state.current_round + 1 < len(state.rounds)
        text = self._say(state, prompts.closing_prompt(state, rnd, has_next))
        state.add_turn("INTERVIEWER", text, meta={"type": "closing"})
        result.messages.append({"text": text, "round_seq": rnd.seq})
        rnd.status = transition(rnd.status, RoundStatus.COMPLETED)
        rnd.ended_at = now
        result.events.append({"type": "round_completed", "round_seq": rnd.seq})
        if has_next:
            state.current_round += 1
            self._start_round(state, now, result, is_first=False)
        else:
            state.status = SessionStatus.COMPLETED
            result.events.append({"type": "session_completed", "early": False})
