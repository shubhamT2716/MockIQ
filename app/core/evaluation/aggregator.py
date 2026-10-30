"""Combine several scoring passes into one calibrated round score."""
import math
import statistics

from ..enums import Verdict
from .models import CompetencyScore, FinalCompetency, PassResult

VERDICT_THRESHOLDS = [
    (4.3, Verdict.STRONG_HIRE),
    (3.6, Verdict.HIRE),
    (3.0, Verdict.LEAN_HIRE),
    (2.4, Verdict.LEAN_NO),
    (0.0, Verdict.NO_HIRE),
]
VERDICT_RANK = {v: i for i, (_, v) in enumerate(VERDICT_THRESHOLDS)}  # 0 best


def verdict_for(score: float | None) -> Verdict | None:
    if score is None:
        return None
    for threshold, v in VERDICT_THRESHOLDS:
        if score >= threshold:
            return v
    return Verdict.NO_HIRE


def confidence_for_spread(spread: float | None, passes: int) -> str:
    if spread is None:
        return "LOW"
    if passes < 2:
        return "MEDIUM"
    if spread <= 0.5:
        return "HIGH"
    if spread <= 1.0:
        return "MEDIUM"
    return "LOW"


def aggregate_competency(name: str, weight: float, per_pass: list[CompetencyScore | None],
                         dropped: int) -> FinalCompetency:
    n = len(per_pass)
    scored = [c for c in per_pass if c is not None and c.score is not None]
    if not scored or len(scored) < math.ceil(n / 2):
        return FinalCompetency(name=name, weight=weight, score=None, spread=None, confidence="LOW",
                               evidence=[], reasoning="Not enough evidence in the transcript to score this.",
                               missed_points=_first_missed(per_pass), dropped_evidence=dropped)
    values = [c.score for c in scored]
    median = round(statistics.median(values) * 2) / 2  # nearest 0.5
    spread = max(values) - min(values)
    rep = min(scored, key=lambda c: abs(c.score - median))
    return FinalCompetency(name=name, weight=weight, score=median, spread=spread,
                           confidence=confidence_for_spread(spread, n), evidence=rep.evidence,
                           reasoning=rep.reasoning, missed_points=rep.missed_points,
                           dropped_evidence=dropped)


def _first_missed(per_pass):
    for c in per_pass:
        if c and c.missed_points:
            return c.missed_points
    return []


def aggregate(passes: list[PassResult], weights: dict[str, float],
              dropped_by_comp: dict[str, int]) -> tuple[list[FinalCompetency], float | None, str]:
    finals = []
    for name, w in weights.items():
        per_pass = [next((c for c in p.competencies if c.name == name), None) for p in passes]
        finals.append(aggregate_competency(name, w, per_pass, dropped_by_comp.get(name, 0)))
    scored = [f for f in finals if f.score is not None]
    weight_covered = sum(f.weight for f in scored)
    if weight_covered < 0.5:
        return finals, None, "LOW"
    overall = round(sum(f.score * f.weight for f in scored) / weight_covered, 2)
    order = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    conf = min((f.confidence for f in scored), key=lambda c: order[c])
    if weight_covered < 0.8 and conf == "HIGH":
        conf = "MEDIUM"
    return finals, overall, conf
