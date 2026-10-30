from pydantic import BaseModel, Field


class Evidence(BaseModel):
    turn: int
    quote: str


class CompetencyScore(BaseModel):
    name: str
    score: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = ""
    missed_points: list[str] = Field(default_factory=list)


class PassResult(BaseModel):
    competencies: list[CompetencyScore]
    strengths: list[str] = Field(default_factory=list)
    model_answers: list[dict] = Field(default_factory=list)


class FinalCompetency(BaseModel):
    name: str
    weight: float
    score: float | None
    spread: float | None
    confidence: str
    evidence: list[Evidence]
    reasoning: str
    missed_points: list[str]
    dropped_evidence: int = 0


class RoundScore(BaseModel):
    round_seq: int
    round_type: str
    title: str
    overall: float | None
    confidence: str
    verdict: str | None
    competencies: list[FinalCompetency]
    strengths: list[str] = Field(default_factory=list)
    model_answers: list[dict] = Field(default_factory=list)
    coverage: list[dict] = Field(default_factory=list)
    passes_used: int = 0
