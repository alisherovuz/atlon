"""Database layer (SQLAlchemy 2.0).

Works with Postgres (Railway) or SQLite (local fallback). All access
goes through the small helper functions at the bottom so the rest of
the bot never touches sessions directly.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column

import config


def _normalized_url(url: str) -> str:
    # Railway sometimes provides the legacy 'postgres://' scheme,
    # but SQLAlchemy expects 'postgresql://'.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


_engine_kwargs: dict = {"pool_pre_ping": True}
if config.DATABASE_URL.startswith("sqlite"):
    # SQLite + multithreaded PTB job queue.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(_normalized_url(config.DATABASE_URL), **_engine_kwargs)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Anyone who has interacted with the bot (used for notifications)."""

    __tablename__ = "users"

    id = mapped_column(BigInteger, primary_key=True)  # telegram user id
    username = mapped_column(String(128), nullable=True)
    full_name = mapped_column(String(256), nullable=True)
    city = mapped_column(String(32), nullable=True)  # preferred city (for notifications)
    is_subscribed = mapped_column(Integer, default=0)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


class Application(Base):
    """A submitted volunteer application."""

    __tablename__ = "applications"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(BigInteger, index=True)
    username = mapped_column(String(128), nullable=True)
    city = mapped_column(String(32))          # city key
    city_name = mapped_column(String(64))     # display name
    full_name = mapped_column(String(256))
    age = mapped_column(Integer, nullable=True)
    phone = mapped_column(String(64), nullable=True)
    interests = mapped_column(Text, nullable=True)
    bio = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


class Event(Base):
    """An event tied to a city, shown in the Events section."""

    __tablename__ = "events"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    city = mapped_column(String(32), index=True)  # city key
    title = mapped_column(String(256))
    date = mapped_column(String(64), nullable=True)
    description = mapped_column(Text, nullable=True)
    # Free-text so admins can write "50 000 so'm", "Bepul", etc.
    price = mapped_column(String(64), nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


# Registration review states
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"


class EventRegistration(Base):
    """A user's registration for an event, pending admin payment review."""

    __tablename__ = "event_registrations"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id = mapped_column(Integer, index=True)
    user_id = mapped_column(BigInteger, index=True)
    username = mapped_column(String(128), nullable=True)
    full_name = mapped_column(String(256))
    age = mapped_column(Integer, nullable=True)
    phone = mapped_column(String(64), nullable=True)
    receipt_file_id = mapped_column(String(256), nullable=True)  # Telegram photo id
    status = mapped_column(String(16), default=PENDING, index=True)
    reviewed_by = mapped_column(BigInteger, nullable=True)
    reviewed_at = mapped_column(DateTime, nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


def _ensure_columns() -> None:
    """Add columns introduced after a table was first created.

    `create_all` never alters existing tables, so a database created by an
    earlier version would be missing e.g. events.price. This adds any such
    column in place, leaving existing rows untouched.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    wanted = {"events": {"price": "VARCHAR(64)"}}

    for table, columns in wanted.items():
        if table not in existing_tables:
            continue  # create_all just built it with every column
        present = {c["name"] for c in inspector.get_columns(table)}
        for column, ddl_type in columns.items():
            if column in present:
                continue
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()


@contextmanager
def session_scope():
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Users ────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str | None, full_name: str | None) -> None:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u is None:
            s.add(User(id=user_id, username=username, full_name=full_name))
        else:
            u.username = username
            u.full_name = full_name


def set_user_subscribed(user_id: int, subscribed: bool) -> None:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u:
            u.is_subscribed = 1 if subscribed else 0


def set_user_city(user_id: int, city_key: str) -> None:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u:
            u.city = city_key


def user_ids_for_city(city_key: str) -> list[int]:
    with session_scope() as s:
        rows = s.execute(select(User.id).where(User.city == city_key)).all()
        return [r[0] for r in rows]


def all_user_ids() -> list[int]:
    with session_scope() as s:
        rows = s.execute(select(User.id)).all()
        return [r[0] for r in rows]


# ── Applications ─────────────────────────────────────────────────

def add_application(data: dict) -> int:
    with session_scope() as s:
        app = Application(
            user_id=data["user_id"],
            username=data.get("username"),
            city=data["city"],
            city_name=data["city_name"],
            full_name=data["full_name"],
            age=data.get("age"),
            phone=data.get("phone"),
            interests=data.get("interests"),
            bio=data.get("bio"),
        )
        s.add(app)
        s.flush()
        return app.id


def all_applications() -> list[Application]:
    with session_scope() as s:
        rows = s.execute(select(Application).order_by(Application.created_at)).scalars().all()
        # detach so callers can read after the session closes
        for r in rows:
            s.expunge(r)
        return list(rows)


def count_applications() -> int:
    with session_scope() as s:
        return s.execute(select(func.count(Application.id))).scalar_one()


# ── Events ───────────────────────────────────────────────────────

def add_event(
    city_key: str,
    title: str,
    date: str | None,
    description: str | None,
    price: str | None = None,
) -> int:
    with session_scope() as s:
        ev = Event(
            city=city_key,
            title=title,
            date=date,
            description=description,
            price=price,
        )
        s.add(ev)
        s.flush()
        return ev.id


def get_event(event_id: int) -> Event | None:
    with session_scope() as s:
        ev = s.get(Event, event_id)
        if ev is not None:
            s.expunge(ev)
        return ev


def events_for_city(city_key: str) -> list[Event]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(Event)
                .where(Event.city == city_key)
                .order_by(Event.created_at.desc())
            )
            .scalars()
            .all()
        )
        for r in rows:
            s.expunge(r)
        return list(rows)


def count_users() -> int:
    with session_scope() as s:
        return s.execute(select(func.count(User.id))).scalar_one()


# ── Event registrations ──────────────────────────────────────────

def add_registration(data: dict) -> int:
    with session_scope() as s:
        reg = EventRegistration(
            event_id=data["event_id"],
            user_id=data["user_id"],
            username=data.get("username"),
            full_name=data["full_name"],
            age=data.get("age"),
            phone=data.get("phone"),
            receipt_file_id=data.get("receipt_file_id"),
            status=PENDING,
        )
        s.add(reg)
        s.flush()
        return reg.id


def get_registration(reg_id: int) -> EventRegistration | None:
    with session_scope() as s:
        reg = s.get(EventRegistration, reg_id)
        if reg is not None:
            s.expunge(reg)
        return reg


def active_registration(event_id: int, user_id: int) -> EventRegistration | None:
    """Return the user's pending or approved registration for an event.

    Rejected registrations are ignored so a user can re-apply with a
    corrected receipt.
    """
    with session_scope() as s:
        reg = (
            s.execute(
                select(EventRegistration)
                .where(EventRegistration.event_id == event_id)
                .where(EventRegistration.user_id == user_id)
                .where(EventRegistration.status.in_([PENDING, APPROVED]))
                .order_by(EventRegistration.created_at.desc())
            )
            .scalars()
            .first()
        )
        if reg is not None:
            s.expunge(reg)
        return reg


def review_registration(reg_id: int, status: str, admin_id: int) -> tuple[bool, EventRegistration | None]:
    """Approve or reject a registration.

    Returns (changed, registration). `changed` is False when another admin
    already reviewed it, so the caller can report that instead of sending a
    second notification to the user.
    """
    with session_scope() as s:
        reg = s.get(EventRegistration, reg_id)
        if reg is None:
            return False, None
        if reg.status != PENDING:
            s.expunge(reg)
            return False, reg
        reg.status = status
        reg.reviewed_by = admin_id
        reg.reviewed_at = datetime.utcnow()
        s.flush()
        s.expunge(reg)
        return True, reg


def registrations_for_event(event_id: int) -> list[EventRegistration]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(EventRegistration)
                .where(EventRegistration.event_id == event_id)
                .order_by(EventRegistration.created_at)
            )
            .scalars()
            .all()
        )
        for r in rows:
            s.expunge(r)
        return list(rows)


def all_registrations() -> list[EventRegistration]:
    with session_scope() as s:
        rows = (
            s.execute(select(EventRegistration).order_by(EventRegistration.created_at))
            .scalars()
            .all()
        )
        for r in rows:
            s.expunge(r)
        return list(rows)


def pending_registrations() -> list[EventRegistration]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(EventRegistration)
                .where(EventRegistration.status == PENDING)
                .order_by(EventRegistration.created_at)
            )
            .scalars()
            .all()
        )
        for r in rows:
            s.expunge(r)
        return list(rows)


def count_registrations(status: str | None = None) -> int:
    with session_scope() as s:
        stmt = select(func.count(EventRegistration.id))
        if status:
            stmt = stmt.where(EventRegistration.status == status)
        return s.execute(stmt).scalar_one()


def all_events() -> list[Event]:
    with session_scope() as s:
        rows = s.execute(select(Event).order_by(Event.created_at)).scalars().all()
        for r in rows:
            s.expunge(r)
        return list(rows)
