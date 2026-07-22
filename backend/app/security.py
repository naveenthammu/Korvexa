import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Tenant, User, UserSession

ROLE_PERMISSIONS = {
    "super_admin": {"*"},
    "platform_admin": {"*"},
    "tenant_owner": {
        "admin:tenant",
        "branch:manage",
        "menu:manage",
        "order:manage",
        "payment:manage",
        "table:manage",
        "inventory:manage",
        "inventory:view",
        "kds:view",
        "kds:manage",
        "report:view",
        "user:manage",
        "employee:view",
        "employee:manage",
        "audit:view",
        "settings:manage",
        "customer:manage",
        "discount:manage",
        "refund:manage",
        "void:manage",
        "shift:manage",
        "drawer:manage",
    },
    "manager": {
        "branch:manage",
        "menu:manage",
        "order:manage",
        "payment:manage",
        "table:manage",
        "inventory:manage",
        "inventory:view",
        "kds:view",
        "kds:manage",
        "report:view",
        "user:manage",
        "employee:view",
        "employee:manage",
        "audit:view",
        "customer:manage",
        "discount:manage",
        "refund:manage",
        "void:manage",
        "shift:manage",
        "drawer:manage",
    },
    "cashier": {"order:manage", "payment:manage", "table:view", "report:view", "shift:manage", "drawer:manage", "customer:view"},
    "waiter": {"order:manage", "table:manage", "customer:manage", "kds:view", "kds:manage"},
    "kitchen_staff": {"kds:manage", "kds:view", "order:view", "menu:view", "inventory:view"},
    "accountant": {"report:view", "employee:view", "employee:manage"},
}

bearer = HTTPBearer(auto_error=False)


def _naive_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_lock_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _secret() -> bytes:
    secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
    if os.getenv("ENVIRONMENT") == "production" and secret == "dev-secret-change-me":
        raise RuntimeError("JWT_SECRET must be set in production")
    return secret.encode("utf-8")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000)
    return hmac.compare_digest(candidate.hex(), digest)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(
    subject: str,
    role: str,
    tenant_id: int | None,
    token_type: str,
    minutes: int,
    jti: str | None = None,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "tenant_id": tenant_id,
        "type": token_type,
        "jti": jti or secrets.token_urlsafe(18),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    signing_input = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}.{_b64(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = _b64(hmac.new(_secret(), signing_input.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(encoded_signature, expected_signature):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(encoded_payload))
        if payload.get("type") != expected_type:
            raise ValueError("bad token type")
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def auth_payload(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return decode_token(credentials.credentials)


def current_user(payload: dict[str, Any] = Depends(auth_payload), db: Session = Depends(get_db)) -> User:
    user = db.get(User, str(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    session_id = str(payload.get("jti") or "")
    session = db.get(UserSession, session_id) if session_id else None
    if (
        session is None
        or session.user_id != user.id
        or session.revoked_at is not None
        or _normalize_lock_time(session.expires_at) <= _naive_utcnow()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    locked_until = _normalize_lock_time(user.locked_until)
    if locked_until and locked_until > _naive_utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account locked")
    if user.tenant_id and user.role not in {"super_admin", "platform_admin"}:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or tenant.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is not active")
    return user


def require_permission(permission: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        permissions = ROLE_PERMISSIONS.get(user.role, set())
        if user.tenant_id and user.role not in {"super_admin", "platform_admin", "tenant_owner"}:
            tenant = db.get(Tenant, user.tenant_id)
            configured = (tenant.settings or {}).get("role_permissions", {}) if tenant else {}
            if isinstance(configured, dict) and isinstance(configured.get(user.role), list):
                permissions = set(configured[user.role])
        custom_permissions = set((user.custom_permissions or {}).get("grants", []))
        if "*" not in permissions and permission not in permissions and permission not in custom_permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency


def check_tenant(user: User, tenant_id: int) -> None:
    if user.role == "super_admin":
        return
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")


class RateLimiter:
    def __init__(self, limit: int = 600):
        self.limit = limit
        self.requests: dict[str, list[float]] = {}

    async def __call__(self, request: Request, call_next):
        now = datetime.now(timezone.utc).timestamp()
        key = request.client.host if request.client else "local"
        window = [stamp for stamp in self.requests.get(key, []) if now - stamp < 60]
        if len(window) >= self.limit:
            headers = {}
            origin = request.headers.get("origin")
            if origin:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
                headers["Vary"] = "Origin"
            return JSONResponse(status_code=429, content={"detail": "Too many requests"}, headers=headers)
        window.append(now)
        self.requests[key] = window
        return await call_next(request)
