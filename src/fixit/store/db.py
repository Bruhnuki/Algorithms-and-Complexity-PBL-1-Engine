"""SQLite (WAL) via SQLAlchemy 2. run_events is append-only (enforced by triggers)."""
from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Cohort(Base):
    __tablename__ = "cohorts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    join_code: Mapped[str] = mapped_column(String(24), unique=True)
    instructor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(12))
    cohort_id: Mapped[int | None] = mapped_column(ForeignKey("cohorts.id"), nullable=True)
    consent_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Session(Base):
    __tablename__ = "sessions"
    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    last_seen_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    seed: Mapped[int] = mapped_column(Integer)
    content_version: Mapped[str] = mapped_column(String(40))
    balance_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="active")
    ending: Mapped[str | None] = mapped_column(String(20), nullable=True)


class RunEvent(Base):
    __tablename__ = "run_events"
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_time: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    client_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("run_id", "client_seq", name="uq_run_client_seq"),)


class TranscriptLine(Base):
    __tablename__ = "transcript_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10))
    latency_ms: Mapped[int] = mapped_column(Integer)
    tone: Mapped[str] = mapped_column(String(10), default="calm")
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(4))
    score: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_user_kind"),)


class AuthEvent(Base):
    __tablename__ = "auth_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    ip_hash: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float)


TRIGGERS = ("CREATE TRIGGER IF NOT EXISTS run_events_no_update BEFORE UPDATE ON run_events "
            "BEGIN SELECT RAISE(ABORT, 'run_events is append-only'); END;",
            "CREATE TRIGGER IF NOT EXISTS run_events_no_delete BEFORE DELETE ON run_events "
            "BEGIN SELECT RAISE(ABORT, 'run_events is append-only'); END;")


def make_engine(path: str):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 5})

    @event.listens_for(eng, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    with eng.begin() as c:
        for t in TRIGGERS:
            c.execute(text(t))
    return eng
