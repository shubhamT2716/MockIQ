from app.core.evaluation.aggregator import aggregate, verdict_for
from app.core.evaluation.evidence_validator import quote_matches, validate_competency
from app.core.evaluation.models import CompetencyScore, Evidence, PassResult
from app.core.evaluation.report import overall_verdict
from app.core.evaluation.models import RoundScore
from app.core.models import Turn


def test_quote_matching_is_fuzzy_but_strict():
    text = "I'd put Redis in front, using cache-aside, and expire keys after ten minutes."
    assert quote_matches("using cache aside and expire keys", text)
    assert not quote_matches("we shard the database by user id", text)


def test_validator_drops_fabricated_evidence():
    turns = {3: Turn(seq=3, round_seq=1, speaker="CANDIDATE", text="I would use BFS from each unvisited land cell."),
             2: Turn(seq=2, round_seq=1, speaker="INTERVIEWER", text="How would you count islands?")}
    c = CompetencyScore(name="approach", score=4, evidence=[
        Evidence(turn=3, quote="use BFS from each unvisited land cell"),
        Evidence(turn=3, quote="union find with path compression"),   # never said
        Evidence(turn=2, quote="How would you count islands"),        # interviewer turn
        Evidence(turn=99, quote="anything")])                          # no such turn
    out, dropped = validate_competency(c, turns)
    assert out.score == 4 and len(out.evidence) == 1 and dropped == 3
    c2 = CompetencyScore(name="approach", score=5, evidence=[Evidence(turn=3, quote="dynamic programming table")])
    out2, _ = validate_competency(c2, turns)
    assert out2.score is None  # no valid evidence -> insufficient signal


def _pass(**scores):
    return PassResult(competencies=[CompetencyScore(name=k, score=v, evidence=[Evidence(turn=1, quote="q")])
                                    for k, v in scores.items()])


def test_aggregate_median_and_confidence():
    passes = [_pass(a=3, b=4), _pass(a=3.5, b=2), _pass(a=3, b=5)]
    finals, overall, conf = aggregate(passes, {"a": 0.5, "b": 0.5}, {})
    fa = next(f for f in finals if f.name == "a")
    fb = next(f for f in finals if f.name == "b")
    assert fa.score == 3 and fa.confidence == "HIGH"
    assert fb.score == 4 and fb.confidence == "LOW"
    assert overall == 3.5 and conf == "LOW"


def test_insufficient_signal_when_majority_null():
    passes = [_pass(a=4), PassResult(competencies=[CompetencyScore(name="a", score=None)]),
              PassResult(competencies=[CompetencyScore(name="a", score=None)])]
    finals, overall, _ = aggregate(passes, {"a": 1.0}, {})
    assert finals[0].score is None and overall is None


def test_verdicts_and_no_hire_cap():
    assert verdict_for(4.5).value == "STRONG_HIRE" and verdict_for(2.0).value == "NO_HIRE"
    rs = [RoundScore(round_seq=1, round_type="DSA", title="a", overall=4.6, confidence="HIGH", verdict="STRONG_HIRE", competencies=[]),
          RoundScore(round_seq=2, round_type="HLD", title="b", overall=2.0, confidence="HIGH", verdict="NO_HIRE", competencies=[])]
    overall, verdict = overall_verdict(rs, {1: 60, 2: 15})
    assert overall > 3.6 and verdict == "LEAN_NO"
