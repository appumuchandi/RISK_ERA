from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator
from fastapi import APIRouter, HTTPException, status, Header, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.auth import JWTAuth
from app.auth.roles import Role
from app.core.database import get_db
from app.models.user import User
from passlib.context import CryptContext
from app.middleware.rate_limit import RateLimiter
from fastapi import Request

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Dedicated rate limiters for auth endpoints (development-safe, not disabled)
_auth_login_limiter = RateLimiter(limit=10, window_seconds=60)
_auth_register_limiter = RateLimiter(limit=5, window_seconds=60)

def _check_auth_rate_limit(request: Request, limiter: RateLimiter):
    client_ip = request.client.host if request.client else "unknown"
    allowed, info = limiter.check(client_ip)
    if not allowed:
        from fastapi.responses import JSONResponse
        import time
        retry_after = info["reset"] - int(time.time())
        headers = {
            "X-Rate-Limit-Limit": str(limiter.limit),
            "X-Rate-Limit-Remaining": "0",
            "X-Rate-Limit-Reset": str(info["reset"]),
            "Retry-After": str(max(retry_after, 1)),
        }
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers=headers,
        )

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    name: str | None = Field(None, max_length=100, description="Display name, optional")

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

class RegisterResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    created_at: str

def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False

def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, http_request: Request, db: Session = Depends(get_db)):
    _check_auth_rate_limit(http_request, _auth_register_limiter)
    # Check duplicate username
    existing_user = db.execute(select(User).where(User.username == request.username)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    existing_email = db.execute(select(User).where(User.email == request.email)).scalar_one_or_none()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    hashed = _hash_password(request.password)
    # Use provided name or username as display, but store username as login
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hashed,
        role=Role.ANALYST,  # default role for new registrations
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

    return RegisterResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    _check_auth_rate_limit(http_request, _auth_login_limiter)
    # Check database users (including seeded demo users)
    db_user = db.execute(select(User).where(User.username == request.username)).scalar_one_or_none()
    if not db_user:
        # Also try email login
        db_user = db.execute(select(User).where(User.email == request.username)).scalar_one_or_none()
    if db_user:
        if not _verify_password(request.password, db_user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = JWTAuth.encode_token(subject=db_user.username)
        return LoginResponse(access_token=token, role=db_user.role, username=db_user.username)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

@router.get("/me")
def me(authorization: str = Header(None), db: Session = Depends(get_db)):
    from app.auth import authenticate_token
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    sub = authenticate_token(authorization)
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    db_user = db.execute(select(User).where(User.username == sub)).scalar_one_or_none()
    if db_user:
        return {"username": db_user.username, "role": db_user.role}
    # If user not found in DB, still return username with default analyst role for backward compatibility
    # (e.g., for tokens issued before user was created, or for test tokens)
    return {"username": sub, "role": Role.ANALYST}
