"""Application service: loads/saves sessions, serialises access, triggers evaluation."""
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from .adapters.db import ProfileRow, ReportRow, SessionRow, WeakTopicRow
from .adapters.resume import extract_text, parse_resume
from .config import Settings
from .core.enums import SessionStatus, TopicStatus
from .core.evaluation.report import build_report
from .core.evaluation.scorer import score_round
from .core.interview_engine import InterviewEngine, TurnResult
from .core.models import SessionState, utcnow
from .core.planner import build_plan
from .core.progress import SessionRecord, build_dashboard
from .core.ports import LLMClient
from .core.rolepacks import RolePack

log = logging.getLogger("mockiq")


class NotFound(Exception):
    pass


class InterviewService:
    def __init__(self, llm: LLMClient, packs: dict[str, RolePack], session_factory, settings: Settings):
        self.llm = llm
        self.packs = packs
        self.db = session_factory
        self.settings = settings
        self.engine = InterviewEngine(llm)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ---------- helpers ----------
    @contextmanager
    def _session_lock(self, session_id: str):
        with self._locks_guard:
            lock = self._locks.setdefault(session_id, threading.Lock())
        with lock:
            yield

    def _load(self, db, session_id: str, user_id: str | None) -> tuple[SessionRow, SessionState]:
        row = db.get(SessionRow, session_id)
        # user_id=None is only used by trusted background jobs.
        if row is None or (user_id is not None and row.user_id != user_id):
            raise NotFound("Interview not found")
        return row, SessionState.model_validate(row.state)

    def _save(self, row: SessionRow, state: SessionState) -> None:
        row.state = state.model_dump(mode="json")
        row.status = state.status.value

    def _view(self, row: SessionRow, state: SessionState) -> dict:
        rnd = state.round
        return {
            "id": row.id,
            "status": state.status.value,
            "mode": row.mode,
            "focus": row.focus,
            "role_title": state.role_title,
            "level": state.level,
            "interviewer": state.persona_name,
            "current_round": rnd.seq,
            "round_started_at": rnd.started_at.isoformat() if rnd.started_at else None,
            "rounds": [{"seq": r.seq, "title": r.title, "type": r.type.value, "status": r.status.value,
                        "duration_min": r.duration_min, "tools": r.tools} for r in state.rounds],
            "transcript": [{"seq": t.seq, "speaker": t.speaker, "text": t.text, "round_seq": t.round_seq}
                           for t in state.turns],
        }

    def _result(self, row, state, result: TurnResult) -> dict:
        view = self._view(row, state)
        view["messages"] = result.messages
        view["events"] = result.events
        return view

    # ---------- catalog ----------
    def role_packs(self) -> list[dict]:
        return [{
            "slug": p.slug, "title": p.title, "domain": p.domain, "interviewer": p.persona.name,
            "stacks": [{"slug": k, "label": v.label} for k, v in p.stacks.items()],
            "levels": [{"key": k, "label": p.levels[k].label,
                        "rounds": [{"index": i, "title": r.title, "type": r.type.value, "duration_min": r.duration_min}
                                   for i, r in enumerate(rs)]}
                       for k, rs in p.rounds_by_level.items()],
        } for p in self.packs.values()]

    # ---------- profiles ----------
    def create_profile(self, user_id: str, text: str | None, filename: str | None, data: bytes | None) -> dict:
        resume_text = (text or "").strip()
        if data:
            resume_text = (extract_text(filename or "", data) + "\n" + resume_text).strip()
        if len(resume_text) < 80:
            raise ValueError("The resume looks empty. Paste the text or upload a PDF, DOCX or TXT file.")
        parsed = parse_resume(self.llm, resume_text, self.settings.max_resume_chars)
        pid = str(uuid.uuid4())
        with self.db() as db:
            db.add(ProfileRow(id=pid, user_id=user_id, filename=filename,
                              resume_text=resume_text[: self.settings.max_resume_chars], parsed=parsed))
            db.commit()
        return {"id": pid, "parsed": parsed, "filename": filename}

    def latest_profile(self, user_id: str) -> dict | None:
        with self.db() as db:
            row = (db.query(ProfileRow).filter(ProfileRow.user_id == user_id)
                   .order_by(ProfileRow.created_at.desc()).first())
            if row is None:
                return None
            return {"id": row.id, "filename": row.filename, "created_at": row.created_at.isoformat(),
                    "summary": (row.parsed or {}).get("summary"), "skills": (row.parsed or {}).get("skills", [])[:12]}

    # ---------- sessions ----------
    def create_session(self, user_id: str, *, profile_id: str | None, role_pack: str, level: str,
                       stack: list[str], round_indexes: list[int] | None, mode: str,
                       focus_weak: bool = False) -> dict:
        pack = self.packs.get(role_pack)
        if pack is None:
            raise ValueError(f"Unknown role: {role_pack}")
        with self.db() as db:
            profile = None
            if profile_id:
                prow = db.get(ProfileRow, profile_id)
                if prow is None or prow.user_id != user_id:
                    raise NotFound("Resume profile not found")
                profile = prow.parsed
            weak = {w.topic for w in db.query(WeakTopicRow).filter(
                WeakTopicRow.user_id == user_id, WeakTopicRow.role_pack == role_pack).all()}
            if focus_weak and not weak:
                raise ValueError("No weak topics recorded for this role yet. Finish an interview first.")
            state = build_plan(pack, level, stack, profile, weak, round_indexes, focus_weak=focus_weak)
            row = SessionRow(id=str(uuid.uuid4()), user_id=user_id, profile_id=profile_id, role_pack=role_pack,
                             level_key=level, mode=mode, focus="weak" if focus_weak else None,
                             status=state.status.value, state={})
            self._save(row, state)
            db.add(row)
            db.commit()
            return self._view(row, state)

    def get_session(self, user_id: str, session_id: str) -> dict:
        with self.db() as db:
            row, state = self._load(db, session_id, user_id)
            return self._view(row, state)

    def start(self, user_id: str, session_id: str) -> dict:
        with self._session_lock(session_id), self.db() as db:
            row, state = self._load(db, session_id, user_id)
            if state.status != SessionStatus.PLANNED:  # idempotent: resuming a started session
                return self._result(row, state, TurnResult())
            result = self.engine.start(state)
            self._save(row, state)
            db.commit()
            return self._result(row, state, result)

    def turn(self, user_id: str, session_id: str, text: str, code: str | None,
             command: str | None = None) -> tuple[dict, bool]:
        if command not in (None, "skip"):
            raise ValueError(f"Unknown command: {command}")
        if command is None and (not text or not text.strip()):
            raise ValueError("Say or type an answer first.")
        with self._session_lock(session_id), self.db() as db:
            row, state = self._load(db, session_id, user_id)
            if command == "skip":
                result = self.engine.skip_question(state, code)
            else:
                result = self.engine.handle_candidate_turn(state, text, code)
            self._save(row, state)
            completed = state.status == SessionStatus.COMPLETED
            if completed:
                self._ensure_report_row(db, session_id)
            db.commit()
            return self._result(row, state, result), completed

    def end(self, user_id: str, session_id: str) -> dict:
        with self._session_lock(session_id), self.db() as db:
            row, state = self._load(db, session_id, user_id)
            result = self.engine.end_early(state, utcnow())
            self._save(row, state)
            self._ensure_report_row(db, session_id)
            db.commit()
            return self._result(row, state, result)

    def _ensure_report_row(self, db, session_id: str) -> None:
        if db.get(ReportRow, session_id) is None:
            db.add(ReportRow(session_id=session_id, status="PENDING"))

    # ---------- evaluation ----------
    def evaluate_session(self, session_id: str) -> None:
        """Runs in the background after the session completes."""
        try:
            with self.db() as db:
                row, state = self._load(db, session_id, None)
            user_id = row.user_id
            pack = self.packs[state.role_pack]
            rounds = [r for r in state.rounds if r.candidate_turns > 0]
            with ThreadPoolExecutor(max_workers=max(1, len(rounds))) as ex:
                futures = [ex.submit(score_round, state, r, pack, self.llm, self.settings.eval_passes) for r in rounds]
                scores = []
                for f in futures:
                    try:
                        scores.append(f.result())
                    except Exception:
                        log.exception("Round evaluation failed for %s", session_id)
            body = build_report(state, sorted(scores, key=lambda s: s.round_seq), self.llm)
            with self.db() as db:
                rep = db.get(ReportRow, session_id)
                rep.status, rep.body, rep.error = "READY", body, None
                self._update_weak_topics(db, user_id, state)
                db.commit()
        except Exception as e:
            log.exception("Report failed for %s", session_id)
            with self.db() as db:
                rep = db.get(ReportRow, session_id)
                if rep:
                    rep.status, rep.error = "FAILED", str(e)
                    db.commit()

    def _update_weak_topics(self, db, user_id: str, state: SessionState) -> None:
        for r in state.rounds:
            for t in r.topics:
                existing = db.get(WeakTopicRow, (user_id, state.role_pack, t.name))
                if t.status in (TopicStatus.MISSED, TopicStatus.PARTIAL, TopicStatus.SKIPPED):
                    if existing:
                        existing.times_missed += 1
                        existing.last_status = t.status.value
                    else:
                        db.add(WeakTopicRow(user_id=user_id, role_pack=state.role_pack, topic=t.name, times_missed=1,
                                            last_status=t.status.value))
                elif t.status == TopicStatus.COVERED and existing:
                    db.delete(existing)

    def _owned_report(self, db, user_id: str, session_id: str) -> ReportRow:
        self._load(db, session_id, user_id)  # ownership check
        rep = db.get(ReportRow, session_id)
        if rep is None:
            raise NotFound("This interview has not finished yet.")
        return rep

    def get_report(self, user_id: str, session_id: str) -> dict:
        with self.db() as db:
            rep = self._owned_report(db, user_id, session_id)
            return {"status": rep.status, "body": rep.body, "error": rep.error, "rating": rep.user_rating}

    def rate_report(self, user_id: str, session_id: str, rating: int) -> None:
        with self.db() as db:
            rep = self._owned_report(db, user_id, session_id)
            rep.user_rating = rating
            db.commit()

    def weak_topics(self, user_id: str, role_pack: str | None = None, limit: int = 50) -> list[dict]:
        with self.db() as db:
            q = db.query(WeakTopicRow).filter(WeakTopicRow.user_id == user_id)
            if role_pack:
                q = q.filter(WeakTopicRow.role_pack == role_pack)
            rows = q.order_by(WeakTopicRow.times_missed.desc(), WeakTopicRow.updated_at.desc()).limit(limit).all()
            titles = {p.slug: p.title for p in self.packs.values()}
            return [{"topic": r.topic, "role_pack": r.role_pack, "role": titles.get(r.role_pack, r.role_pack),
                     "times_missed": r.times_missed, "last_status": r.last_status} for r in rows]

    # ---------- dashboard ----------
    def dashboard(self, user_id: str, tz_offset_min: int = 0, role_pack: str | None = None) -> dict:
        with self.db() as db:
            q = db.query(SessionRow).filter(SessionRow.user_id == user_id)
            if role_pack:
                q = q.filter(SessionRow.role_pack == role_pack)
            rows = q.order_by(SessionRow.created_at.desc()).limit(200).all()
            reports = {r.session_id: r for r in db.query(ReportRow).filter(
                ReportRow.session_id.in_([x.id for x in rows])).all()} if rows else {}
        records = []
        for row in rows:
            rep = reports.get(row.id)
            records.append(SessionRecord(
                id=row.id, created_at=row.created_at, role_pack=row.role_pack, focus=row.focus,
                state=SessionState.model_validate(row.state),
                report_status=rep.status if rep else None, report=rep.body if rep else None))
        dash = build_dashboard(records, self.weak_topics(user_id, role_pack, limit=10), utcnow(), tz_offset_min)
        last = next((r for r in rows), None)
        dash["last_setup"] = ({"role_pack": last.role_pack, "level": last.level_key} if last else None)
        return dash
