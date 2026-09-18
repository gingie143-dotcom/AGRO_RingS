import hashlib
import hmac
from datetime import timedelta
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .config import settings
from .db import session
from .models import User, now

hasher = PasswordHasher()


def phone_hash(phone):
    return hmac.new(settings().secret_key.encode(), phone.encode(), hashlib.sha256).hexdigest()


def verify_password(stored, candidate):
    try:
        return hasher.verify(stored, candidate)
    except VerificationError:
        return False


def token(user):
    return jwt.encode(
        {"sub": user.id, "exp": now() + timedelta(hours=8), "iat": now()},
        settings().secret_key,
        algorithm="HS256",
    )


def current_user(request: Request, db=Depends(session)):
    raw = request.cookies.get("session")
    if not raw:
        raise HTTPException(401, "Требуется вход")
    try:
        claims = jwt.decode(
            raw, settings().secret_key, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
        user = db.get(User, claims["sub"])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Сессия истекла")
    if not user or not user.active:
        raise HTTPException(401, "Пользователь недоступен")
    return user


def operator(user=Depends(current_user)):
    if user.role not in ("admin", "operator"):
        raise HTTPException(403, "Недостаточно прав")
    return user


def admin(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Требуются права администратора")
    return user


def service(request: Request):
    raw = request.headers.get("authorization", "")
    if not hmac.compare_digest(raw, "Bearer " + settings().service_token):
        raise HTTPException(401, "Service authentication required")


def bootstrap(db):
    if not db.scalar(select(User).where(User.username == settings().admin_username)):
        db.add(
            User(
                username=settings().admin_username,
                password_hash=hasher.hash(settings().admin_password),
                role="admin",
            )
        )
        db.commit()
