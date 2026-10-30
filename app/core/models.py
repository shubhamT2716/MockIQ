"""Domain models. Pure pydantic, no framework or DB imports."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .enums import NextAction, RoundStatus, RoundType, SessionStatus, TopicStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TopicState(BaseModel):
    name: str
    target_depth: int
    source: Literal["mandatory", "optional", "stack", "resume", "weak"] = "mandatory"
    seed_question: str | None = None
    key_points: list[str] = Field(default_factory=list)
    depth_reached: int = 0
    probes: int = 0
    hints: int = 0
    status: TopicStatus = TopicStatus.NOT_STARTED
    key_points_hit: list[str] = Field(default_factory=list)
    key_points_missed: list[str] = Field(default_factory=list)

    def close(self) -> None:
        if self.depth_reached >= self.target_depth:
            self.status = TopicStatus.COVERED
        elif self.depth_reached >= 2:
            self.status = TopicStatus.PARTIAL
        else:
            self.status = TopicStatus.MISSED


class RoundState(BaseModel):
    seq: int
    type: RoundType
    title: str
    duration_min: int
    target_depth: int
    competencies: dict[str, float]
    tools: list[str] = Field(default_factory=list)
    max_probes: int = 3
    max_hints: int = 1
    max_candidate_turns: int = 20
    topics: list[TopicState]
    # runtime
    status: RoundStatus = RoundStatus.PLANNED
    topic_index: int = 0
    candidate_turns: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def current_topic(self) -> TopicState | None:
        if 0 <= self.topic_index < len(self.topics):
            return self.topics[self.topic_index]
        return None

    @property
    def next_topic(self) -> TopicState | None:
        i = self.topic_index + 1
        return self.topics[i] if i < len(self.topics) else None

    def elapsed_sec(self, now: datetime) -> float:
        return (now - self.started_at).total_seconds() if self.started_at else 0.0


class Turn(BaseModel):
    seq: int
    round_seq: int
    speaker: Literal["INTERVIEWER", "CANDIDATE"]
    text: str
    at: datetime = Field(default_factory=utcnow)
    code: str | None = None
    meta: dict = Field(default_factory=dict)


class SessionState(BaseModel):
    role_pack: str
    role_title: str
    level: str
    level_bar: str
    stack: list[str] = Field(default_factory=list)
    persona_name: str
    persona_style: str
    resume_summary: str | None = None
    status: SessionStatus = SessionStatus.PLANNED
    current_round: int = 0
    rounds: list[RoundState]
    turns: list[Turn] = Field(default_factory=list)

    @property
    def round(self) -> RoundState:
        return self.rounds[self.current_round]

    def add_turn(self, speaker, text, *, code=None, meta=None) -> Turn:
        t = Turn(
            seq=len(self.turns) + 1,
            round_seq=self.round.seq,
            speaker=speaker,
            text=text,
            code=code,
            meta=meta or {},
        )
        self.turns.append(t)
        return t

    def round_turns(self, seq: int) -> list[Turn]:
        return [t for t in self.turns if t.round_seq == seq]


class TurnDecision(BaseModel):
    answer_quality: Literal["strong", "partial", "weak", "off_topic", "dont_know", "unclear"]
    estimated_depth: int = Field(ge=0, le=5)
    key_points_hit: list[str] = Field(default_factory=list)
    key_points_missed: list[str] = Field(default_factory=list)
    next_action: NextAction
    utterance: str


TURN_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_quality": {
            "type": "string",
            "enum": ["strong", "partial", "weak", "off_topic", "dont_know", "unclear"],
        },
        "estimated_depth": {
            "type": "integer",
            "minimum": 0,
            "maximum": 5,
            "description": "Deepest level of the depth ladder the candidate has shown on the current topic so far.",
        },
        "key_points_hit": {"type": "array", "items": {"type": "string"}},
        "key_points_missed": {"type": "array", "items": {"type": "string"}},
        "next_action": {"type": "string", "enum": [a.value for a in NextAction]},
        "utterance": {
            "type": "string",
            "description": "Exactly what the interviewer says next. Spoken style, at most two sentences unless stating a problem.",
        },
    },
    "required": ["answer_quality", "estimated_depth", "next_action", "utterance"],
}
