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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

# Demo credential store — synthetic, not production (kept for backward compatibility)
DEMO_USERS = {
    "analyst": {"password": "analyst123", "role": Role.ANALYST},
    "admin": {"password": "admin123", "role": Role.ADMIN},
    "Admin1": {"password": "Admin@1234", "role": Role.ADMIN},
    "demo": {"password": "demo", "role": Role.ANALYST},
}

def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False

def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    # Check duplicate username
    existing_user = db.execute(select(User).where(User.username == request.username)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    existing_email = db.execute(select(User).where(User.email == request.email)).scalar_one_or_none()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    # Also check against demo users to prevent confusion
    if request.username in DEMO_USERS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    # Check demo email not needed

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
def login(request: LoginRequest, db: Session = Depends(get_db)):
    # First check demo users (kept for backward compatibility and tests)
    user = DEMO_USERS.get(request.username)
    if user:
        if request.password != user["password"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = JWTAuth.encode_token(subject=request.username)
        return LoginResponse(access_token=token, role=user["role"], username=request.username)

    # Allow any username with password "demo" for easy demo access
    if request.password == "demo":
        token = JWTAuth.encode_token(subject=request.username)
        return LoginResponse(access_token=token, role=Role.ANALYST, username=request.username)

    # Check database users
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
    # Check demo users first, then DB
    user = DEMO_USERS.get(sub)
    if user:
        return {"username": sub, "role": user["role"]}
    db_user = db.execute(select(User).where(User.username == sub)).scalar_one_or_none()
    if db_user:
        return {"username": db_user.username, "role": db_user.role}
    # Fallback for any demo "password demo" users
    return {"username": sub, "role": Role.ANALYST}
