"""Builds the progress dashboard from a user's sessions and reports. Pure functions."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean

from .enums import SessionStatus
from .models import SessionState


@dataclass
class SessionRecord:
    id: str
    created_at: datetime
    role_pack: str
    focus: str | None
    state: SessionState
    report_status: str | None
    report: dict | None


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)  # SQLite returns naive UTC


def _local_date(ts: datetime, tz_offset_min: int) -> date:
    """tz_offset_min follows JS getTimezoneOffset(): minutes to ADD to local time to get UTC (IST = -330)."""
    ts = _aware(ts)
    return (ts.astimezone(timezone.utc) - timedelta(minutes=tz_offset_min)).date()


def practice_minutes(state: SessionState) -> float:
    total = 0.0
    for r in state.rounds:
        if not r.started_at:
            continue
        times = [t.at for t in state.turns if t.round_seq == r.seq]
        end = r.ended_at or (max(times) if times else r.started_at)
        total += min(max(0.0, (end - r.started_at).total_seconds() / 60), r.duration_min * 2)
    return total


def streak_days(active_days: set[date], today: date) -> int:
    """Consecutive days of practice ending today, or yesterday if today has none yet."""
    day = today if today in active_days else today - timedelta(days=1)
    n = 0
    while day in active_days:
        n += 1
        day -= timedelta(days=1)
    return n


def competency_progress(records: list[SessionRecord]) -> list[dict]:
    samples: dict[str, list[float]] = {}
    for rec in sorted(records, key=lambda r: r.created_at):
        if rec.report_status != "READY" or not rec.report:
            continue
        for rnd in rec.report.get("rounds", []):
            for c in rnd.get("competencies", []):
                if c.get("score") is not None:
                    samples.setdefault(c["name"], []).append(float(c["score"]))
    out = []
    for name, vals in samples.items():
        recent = vals[-3:]
        earlier = vals[:-3]
        out.append({
            "name": name,
            "avg": round(mean(vals), 2),
            "recent": round(mean(recent), 2),
            "change": round(mean(recent) - mean(earlier), 2) if earlier else None,
            "samples": len(vals),
        })
    return sorted(out, key=lambda c: c["avg"])


def build_dashboard(records: list[SessionRecord], weak_topics: list[dict], now: datetime,
                    tz_offset_min: int = 0) -> dict:
    for r in records:
        r.created_at = _aware(r.created_at)
    records = sorted(records, key=lambda r: r.created_at)
    trend, history, in_progress = [], [], []
    active_days: set[date] = set()
    minutes = 0.0

    for rec in records:
        s = rec.state
        for t in s.turns:
            if t.speaker == "CANDIDATE":
                active_days.add(_local_date(t.at, tz_offset_min))
        minutes += practice_minutes(s)
        body = rec.report if rec.report_status == "READY" else None
        overall = body.get("overall") if body else None
        verdict = body.get("verdict") if body else None
        if overall is not None:
            trend.append({"session_id": rec.id, "date": rec.created_at.isoformat(), "role": s.role_title,
                          "level": s.level, "overall": overall, "verdict": verdict})
        history.append({"session_id": rec.id, "date": rec.created_at.isoformat(), "role": s.role_title,
                        "role_pack": rec.role_pack, "level": s.level, "status": s.status.value,
                        "focus": rec.focus, "report_status": rec.report_status,
                        "overall": overall, "verdict": verdict,
                        "rounds": [r.title for r in s.rounds]})
        if s.status in (SessionStatus.PLANNED, SessionStatus.LIVE):
            done = sum(1 for r in s.rounds if r.status.value in ("COMPLETED", "ENDED_EARLY", "SKIPPED"))
            in_progress.append({"session_id": rec.id, "role": s.role_title, "level": s.level, "focus": rec.focus,
                                "date": rec.created_at.isoformat(), "rounds_done": done,
                                "rounds_total": len(s.rounds), "current_round": s.round.title})

    recent_scores = [t["overall"] for t in trend[-5:]]
    return {
        "stats": {
            "interviews": len(records),
            "completed": sum(1 for r in records if r.state.status == SessionStatus.COMPLETED),
            "practice_minutes": round(minutes),
            "streak_days": streak_days(active_days, _local_date(now, tz_offset_min)),
            "avg_recent": round(mean(recent_scores), 2) if recent_scores else None,
            "best": max((t["overall"] for t in trend), default=None),
        },
        "trend": trend[-30:],
        "competencies": competency_progress(records),
        "weak_topics": weak_topics,
        "in_progress": list(reversed(in_progress)),
        "history": list(reversed(history))[:50],
    }
