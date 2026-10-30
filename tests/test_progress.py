import random
from datetime import datetime, timedelta, timezone

from app.core.planner import build_plan
from app.core.progress import SessionRecord, build_dashboard, competency_progress, streak_days
from app.core.enums import SessionStatus


def test_streak_counts_today_or_yesterday():
    d = datetime(2026, 10, 20).date()
    days = {d - timedelta(days=i) for i in (1, 2, 3)}
    assert streak_days(days, d) == 3          # practised up to yesterday: streak still alive
    assert streak_days(days | {d}, d) == 4
    assert streak_days({d - timedelta(days=3)}, d) == 0


def _report(scores, overall):
    return {"overall": overall, "verdict": "HIRE",
            "rounds": [{"competencies": [{"name": k, "score": v} for k, v in scores.items()]}]}


def _rec(packs, i, scores, overall, status=SessionStatus.COMPLETED):
    st = build_plan(packs["backend-sde"], "L2", [], None, round_indexes=[0], rng=random.Random(i))
    st.status = status
    return SessionRecord(id=f"s{i}", created_at=datetime(2026, 10, 1 + i, tzinfo=timezone.utc),
                         role_pack="backend-sde", focus=None, state=st,
                         report_status="READY" if overall else None,
                         report=_report(scores, overall) if overall else None)


def test_competency_trend(packs):
    recs = [_rec(packs, i, {"approach": s, "correctness": 3}, 3.0) for i, s in enumerate([2, 2, 2, 4, 4, 4])]
    comps = {c["name"]: c for c in competency_progress(recs)}
    assert comps["approach"]["recent"] == 4 and comps["approach"]["change"] == 2
    assert comps["correctness"]["change"] == 0
    assert competency_progress(recs)[0]["avg"] <= competency_progress(recs)[-1]["avg"]  # weakest first


def test_dashboard_shape(packs):
    recs = [_rec(packs, 0, {"approach": 3}, 3.2), _rec(packs, 1, {"approach": 4}, 4.0),
            _rec(packs, 2, {}, None, status=SessionStatus.LIVE)]
    d = build_dashboard(recs, [{"topic": "Caching"}], datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert d["stats"]["interviews"] == 3 and d["stats"]["completed"] == 2
    assert [t["overall"] for t in d["trend"]] == [3.2, 4.0]
    assert d["stats"]["avg_recent"] == 3.6 and d["stats"]["best"] == 4.0
    assert d["in_progress"][0]["session_id"] == "s2"
    assert d["history"][0]["session_id"] == "s2"  # newest first


def test_streak_uses_local_timezone(packs):
    rec = _rec(packs, 0, {"approach": 3}, 3.0)
    st = rec.state
    st.current_round = 0
    # 20:00 UTC on Oct 19 is 01:30 on Oct 20 in India.
    st.add_turn("CANDIDATE", "answer")
    st.turns[-1].at = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)
    now = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)
    assert build_dashboard([rec], [], now, tz_offset_min=-330)["stats"]["streak_days"] == 1
    assert build_dashboard([rec], [], now + timedelta(days=1), tz_offset_min=0)["stats"]["streak_days"] == 0


def test_focus_plan_puts_weak_topics_first(packs):
    weak = {"Caching", "Reliability and failure modes"}
    st = build_plan(packs["backend-sde"], "L2", [], None, weak_topics=weak, focus_weak=True, rng=random.Random(1))
    assert [r.title for r in st.rounds] == ["System design"]
    assert [t.source for t in st.rounds[0].topics[:2]] == ["weak", "weak"]
