from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def _now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProfileRow(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_text: Mapped[str] = mapped_column(Text)
    parsed: Mapped[dict] = mapped_column(JSON)


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    role_pack: Mapped[str] = mapped_column(String(64), index=True)
    level_key: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(8))
    focus: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "weak" for gap practice
    status: Mapped[str] = mapped_column(String(16), index=True)
    state: Mapped[dict] = mapped_column(JSON)


class ReportRow(Base):
    __tablename__ = "reports"
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(16))  # PENDING | READY | FAILED
    body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WeakTopicRow(Base):
    __tablename__ = "weak_topics"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_pack: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic: Mapped[str] = mapped_column(String(200), primary_key=True)
    times_missed: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class OutdatedDatabase(RuntimeError):
    pass


def _check_schema(engine) -> None:
    insp = inspect(engine)
    if "sessions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sessions")}
        if "user_id" not in cols:
            raise OutdatedDatabase(
                "This database was created by Phase 1 (no user accounts). "
                "Delete mockiq.db (it only holds practice data) and restart, or migrate it by hand.")


def make_session_factory(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs = {"connect_args": connect_args, "pool_pre_ping": True}
    # sqlite:///:memory: is a new database per connection unless every session
    # shares one connection. StaticPool keeps accounts and interviews alive
    # for the life of this process, then drops them on shutdown.
    if url in ("sqlite:///:memory:", "sqlite://"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    _check_schema(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
