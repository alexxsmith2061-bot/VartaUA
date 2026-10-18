"""VARTA accounts: verified Telegram Mini App login and minimal private profiles."""
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

router = APIRouter(prefix="/api/account", tags=["account"])
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
_engine = None
_Session = None


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "varta_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nickname_key: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    city: Mapped[str] = mapped_column(String(100), default="Львів")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Preference(Base):
    __tablename__ = "varta_preferences"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("varta_users.id", ondelete="CASCADE"), primary_key=True)
    power_queue: Mapped[str | None] = mapped_column(String(3), nullable=True)
    topics: Mapped[str] = mapped_column(String(500), default="[]")


def init_database():
    """Call only when DATABASE_URL is configured. No ephemeral Render fallback."""
    global _engine, _Session
    if not DATABASE_URL:
        return
    url = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    _engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(_engine, expire_on_commit=False)


def session():
    if not _Session:
        raise HTTPException(503, "База акаунтів ще не налаштована")
    with _Session() as db:
        yield db


def verify_telegram_init_data(raw: str, now: int | None = None) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(503, "Telegram-авторизацію не налаштовано")
    if len(raw) > 8192:
        raise HTTPException(401, "Неправильні дані авторизації")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise HTTPException(401, "Неправильні дані авторизації")
    data = dict(pairs)
    if len(pairs) != len(data) or "hash" not in data:
        raise HTTPException(401, "Неправильні дані авторизації")
    received_hash = data.pop("hash")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected):
        raise HTTPException(401, "Невірний підпис Telegram")
    current = int(time.time()) if now is None else now
    try:
        auth_date = int(data["auth_date"])
        user = json.loads(data["user"])
        telegram_id = int(user["id"])
        if auth_date > current + 60 or current - auth_date > 3600 or telegram_id <= 0:
            raise ValueError("Expired or invalid")
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Прострочені або неправильні дані Telegram")
    return user


def require_user(authorization: str | None = Header(default=None), db: Session = Depends(session)) -> User:
    if not SESSION_SECRET:
        raise HTTPException(503, "Секрет сесій не налаштований")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Потрібна авторизація")
    try:
        payload = jwt.decode(authorization[7:], SESSION_SECRET, algorithms=["HS256"], audience="varta")
        user_id = payload["sub"]
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, "Недійсна сесія")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Акаунт не знайдено")
    return user


class LoginRequest(BaseModel):
    init_data: str = Field(min_length=10, max_length=8192)


class ProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=100)
    notifications_enabled: bool | None = None
    power_queue: str | None = None
    topics: list[str] | None = Field(default=None, max_length=12)


def public_profile(user: User, db: Session) -> dict:
    pref = db.get(Preference, user.id)
    return {
        "id": user.id, "nickname": user.nickname, "city": user.city,
        "avatar_url": user.avatar_url, "notifications_enabled": user.notifications_enabled,
        "power_queue": pref.power_queue if pref else None,
        "topics": json.loads(pref.topics) if pref else [],
    }


@router.post("/telegram")
def login(request: LoginRequest, db: Session = Depends(session)):
    if not SESSION_SECRET or len(SESSION_SECRET) < 32:
        raise HTTPException(503, "Секрет сесій не налаштований")
    tg = verify_telegram_init_data(request.init_data)
    user = db.scalar(select(User).where(User.telegram_id == int(tg["id"])))
    if not user:
        user = User(telegram_id=int(tg["id"]))
        db.add(user)
        db.flush()
        db.add(Preference(user_id=user.id))
        db.commit()
    token = jwt.encode({"sub": user.id, "aud": "varta", "iat": int(time.time()),
                        "exp": int(time.time()) + 86400}, SESSION_SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "profile": public_profile(user, db)}


@router.get("/me")
def get_me(user: User = Depends(require_user), db: Session = Depends(session)):
    return public_profile(user, db)


@router.patch("/me")
def update_me(change: ProfileUpdate, user: User = Depends(require_user), db: Session = Depends(session)):
    fields = change.model_fields_set
    if "nickname" in fields:
        name = (change.nickname or "").strip()
        if name and not re.fullmatch(r"[\w\-]{3,32}", name, flags=re.UNICODE):
            raise HTTPException(422, "Нік: 3–32 символи, літери, цифри, _ або -")
        user.nickname = name or None
        user.nickname_key = name.casefold() if name else None
    if "city" in fields:
        city = (change.city or "").strip()
        if not city or len(city) > 100:
            raise HTTPException(422, "Невірне місто")
        user.city = city
    if "notifications_enabled" in fields:
        user.notifications_enabled = bool(change.notifications_enabled)
    pref = db.get(Preference, user.id)
    if not pref:
        pref = Preference(user_id=user.id)
        db.add(pref)
    if "power_queue" in fields:
        queue = change.power_queue
        if queue is not None and not re.fullmatch(r"[1-6]\.[12]", queue):
            raise HTTPException(422, "Невідома черга")
        pref.power_queue = queue
    if "topics" in fields:
        topics = change.topics or []
        if any(not isinstance(t, str) or not re.fullmatch(r"[\w\- ]{1,30}", t, flags=re.UNICODE) for t in topics):
            raise HTTPException(422, "Невірна тема")
        pref.topics = json.dumps(list(dict.fromkeys(topics)), ensure_ascii=False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Цей нік уже зайнятий")
    db.refresh(user)
    return public_profile(user, db)


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(require_user), db: Session = Depends(session)):
    pref = db.get(Preference, user.id)
    if pref:
        db.delete(pref)
    db.delete(user)
    db.commit()
