"""Deterministic check that every piece of evidence really exists in the transcript."""
import re
from difflib import SequenceMatcher

from ..models import Turn
from .models import CompetencyScore, Evidence

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def quote_matches(quote: str, text: str, threshold: float = 0.85) -> bool:
    q, t = _tokens(quote), _tokens(text)
    if not q or not t:
        return False
    qs, ts = " ".join(q), " ".join(t)
    if qs in ts:
        return True
    n = len(q)
    best = 0.0
    for i in range(0, max(1, len(t) - n + 1)):
        window = " ".join(t[i:i + n])
        best = max(best, SequenceMatcher(None, qs, window).ratio())
        if best >= threshold:
            return True
    return False


_NOT_AN_ANSWER = re.compile(
    r"\b(?:no questions?|explain the problem|what(?:'s| is) the (?:question|problem)|"
    r"there is no|didn'?t ask|repeat the question|i don'?t know|which problem)\b",
    re.I,
)


def turn_is_answer(turn: Turn) -> bool:
    """A candidate turn that could support a score. Comments that no question was asked do not."""
    if turn.speaker != "CANDIDATE" or (turn.meta or {}).get("command") == "skip":
        return False
    if turn.code and len(turn.code.strip()) >= 20:
        return True
    text = (turn.text or "").strip()
    if not text or _NOT_AN_ANSWER.search(text):
        return False
    return len(text.split()) >= 6


def transcript_has_answer(turns: dict[int, Turn]) -> bool:
    return any(turn_is_answer(t) for t in turns.values())


def validate_competency(c: CompetencyScore, turns: dict[int, Turn]) -> tuple[CompetencyScore, int]:
    """Keep only evidence that points at a real candidate turn and quotes it.
    If a score is left with no valid evidence it becomes None (insufficient signal)."""
    valid: list[Evidence] = []
    dropped = 0
    for ev in c.evidence:
        turn = turns.get(ev.turn)
        haystack = f"{turn.text}\n{turn.code or ''}" if turn else ""
        if turn and turn.speaker == "CANDIDATE" and quote_matches(ev.quote, haystack):
            valid.append(ev)
        else:
            dropped += 1
    score = c.score if valid else None
    return c.model_copy(update={"evidence": valid, "score": score}), dropped
