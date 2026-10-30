"""Builds the final session report from round scores."""
from ..enums import TopicStatus, Verdict
from ..models import SessionState
from ..ports import LLMClient
from .aggregator import VERDICT_RANK, verdict_for
from .models import RoundScore

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "3-4 sentence honest summary addressed to the candidate."},
        "study_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "why": {"type": "string"},
                    "how_to_practice": {"type": "string"},
                    "priority": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["topic", "why", "how_to_practice", "priority"],
            },
        },
        "next_mock_focus": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "study_plan", "next_mock_focus"],
}


def overall_verdict(scores: list[RoundScore], durations: dict[int, int]) -> tuple[float | None, str | None]:
    scored = [s for s in scores if s.overall is not None]
    if not scored:
        return None, None
    total = sum(durations[s.round_seq] for s in scored)
    overall = round(sum(s.overall * durations[s.round_seq] for s in scored) / total, 2)
    verdict = verdict_for(overall)
    if any(s.verdict == Verdict.NO_HIRE.value for s in scored) and VERDICT_RANK[verdict] < VERDICT_RANK[Verdict.LEAN_NO]:
        verdict = Verdict.LEAN_NO  # one failing round caps the overall, like a hiring committee
    return overall, verdict.value


def missed_topics(state: SessionState) -> list[dict]:
    out = []
    for r in state.rounds:
        for t in r.topics:
            if t.status in (TopicStatus.MISSED, TopicStatus.PARTIAL, TopicStatus.NOT_REACHED, TopicStatus.SKIPPED):
                out.append({"round_seq": r.seq, "topic": t.name, "status": t.status.value,
                            "depth_reached": t.depth_reached, "target_depth": t.target_depth,
                            "key_points_missed": t.key_points_missed})
    return out


def build_report(state: SessionState, scores: list[RoundScore], llm: LLMClient | None) -> dict:
    durations = {r.seq: r.duration_min for r in state.rounds}
    overall, verdict = overall_verdict(scores, durations)
    gaps = missed_topics(state)
    body = {
        "role": state.role_title,
        "level": state.level,
        "overall": overall,
        "verdict": verdict,
        "rounds": [s.model_dump(mode="json") for s in scores],
        "rounds_not_attempted": [
            {"seq": r.seq, "title": r.title} for r in state.rounds
            if r.seq not in {s.round_seq for s in scores}
        ],
        "missed_topics": gaps,
        "summary": None,
        "study_plan": [],
        "next_mock_focus": [],
    }
    fallback_plan = [{"topic": g["topic"], "why": f"Reached depth {g['depth_reached']} of {g['target_depth']}.",
                      "how_to_practice": "Review the key points, then explain it out loud in a new mock.",
                      "priority": 1 if g["status"] in ("MISSED", "SKIPPED") else 2} for g in gaps[:6]]
    if llm is None or not scores:
        body["summary"] = "Not enough of the interview was completed to give a detailed summary."
        body["study_plan"] = fallback_plan
        return body
    digest = []
    for s in scores:
        comp = ", ".join(f"{c.name}={c.score}" for c in s.competencies)
        missed = "; ".join(p for c in s.competencies for p in c.missed_points[:3])
        digest.append(f"Round {s.round_seq} {s.title}: overall {s.overall} ({s.verdict}); {comp}. Missed: {missed}")
    gap_text = "\n".join(f"- {g['topic']} ({g['status']}, depth {g['depth_reached']}/{g['target_depth']}): "
                         f"{', '.join(g['key_points_missed'][:4])}" for g in gaps)
    try:
        out = llm.structured(
            role="evaluator",
            system="You write concise, honest, encouraging interview feedback. No fluff. Address the candidate as 'you'.",
            user=(f"Role {state.role_title}, level {state.level}. Overall verdict {verdict} ({overall}).\n"
                  + "\n".join(digest) + f"\nTopic gaps:\n{gap_text or 'none'}\n"
                  "Write the summary, a prioritised study plan (max 6 items, concrete practice suggestions), and 2-4 focus areas for the next mock. "
                  "If the overall score is missing, say plainly that the candidate did not give enough of an answer to score. Do not invent strengths or a positive verdict."),
            tool_name="report_summary", tool_description="Final feedback summary.",
            schema=SUMMARY_SCHEMA, temperature=0.4, max_tokens=1500,
        )
        body["summary"] = out.get("summary")
        body["study_plan"] = sorted(out.get("study_plan", []), key=lambda x: x.get("priority", 3))[:6]
        body["next_mock_focus"] = out.get("next_mock_focus", [])[:4]
    except Exception:
        body["summary"] = "Your scores are below. The written summary could not be generated this time."
        body["study_plan"] = fallback_plan
    return body
