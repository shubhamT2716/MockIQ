"""Sign-up, sign-in and cookie sessions."""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from .adapters.db import AuthSessionRow, UserRow
from .core.auth import (DUMMY_HASH, AuthError, LoginLimiter, check_password_rules, hash_password,
                        new_token, normalize_email, token_hash, verify_password)

SESSION_DAYS = 30


@dataclass
class User:
    id: str
    email: str
    name: str


def _now():
    return datetime.now(timezone.utc)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo


class AuthService:
    def __init__(self, session_factory, limiter: LoginLimiter | None = None):
        self.db = session_factory
        self.limiter = limiter or LoginLimiter()

    def _issue(self, db, user_id: str) -> str:
        token = new_token()
        db.add(AuthSessionRow(token_hash=token_hash(token), user_id=user_id,
                              expires_at=_now() + timedelta(days=SESSION_DAYS)))
        return token

    def signup(self, name: str, email: str, password: str) -> tuple[User, str]:
        email = normalize_email(email)
        name = (name or "").strip()[:100]
        if not name:
            raise AuthError("Enter your name.")
        check_password_rules(password)
        with self.db() as db:
            row = UserRow(id=str(uuid.uuid4()), email=email, name=name, password_hash=hash_password(password))
            db.add(row)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                raise AuthError("An account with this email already exists. Sign in instead.")
            token = self._issue(db, row.id)
            db.commit()
            return User(row.id, row.email, row.name), token

    def login(self, email: str, password: str, ip: str) -> tuple[User, str]:
        try:
            email = normalize_email(email)
        except AuthError:
            raise AuthError("Email or password is incorrect.")
        keys = (f"email:{email}", f"ip:{ip}")
        self.limiter.check(*keys)
        with self.db() as db:
            row = db.query(UserRow).filter(UserRow.email == email).one_or_none()
            ok = verify_password(password or "", row.password_hash if row else DUMMY_HASH)
            if not row or not ok:
                self.limiter.fail(*keys)
                raise AuthError("Email or password is incorrect.")
            self.limiter.reset(f"email:{email}")
            token = self._issue(db, row.id)
            db.commit()
            return User(row.id, row.email, row.name), token

    def user_for_token(self, token: str | None) -> User | None:
        if not token:
            return None
        with self.db() as db:
            sess = db.get(AuthSessionRow, token_hash(token))
            if sess is None:
                return None
            if _aware(sess.expires_at) < _now():
                db.delete(sess)
                db.commit()
                return None
            row = db.get(UserRow, sess.user_id)
            return User(row.id, row.email, row.name) if row else None

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self.db() as db:
            sess = db.get(AuthSessionRow, token_hash(token))
            if sess:
                db.delete(sess)
                db.commit()
