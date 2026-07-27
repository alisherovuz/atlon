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
    created_at = mapped_column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


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

def add_event(city_key: str, title: str, date: str | None, description: str | None) -> int:
    with session_scope() as s:
        ev = Event(city=city_key, title=title, date=date, description=description)
        s.add(ev)
        s.flush()
        return ev.id


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
