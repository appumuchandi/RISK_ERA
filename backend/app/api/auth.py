from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status, Header

from app.auth import JWTAuth
from app.auth.roles import Role

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str

# Demo credential store — synthetic, not production
DEMO_USERS = {
    "analyst": {"password": "analyst123", "role": Role.ANALYST},
    "admin": {"password": "admin123", "role": Role.ADMIN},
    "Admin1": {"password": "Admin@1234", "role": Role.ADMIN},
    "demo": {"password": "demo", "role": Role.ANALYST},
}

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    user = DEMO_USERS.get(request.username)
    # Allow any username with password "demo" for easy demo access, fallback to demo user
    if not user:
        if request.password == "demo":
            user = {"password": "demo", "role": Role.ANALYST}
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if request.password != user["password"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = JWTAuth.encode_token(subject=request.username)
    return LoginResponse(access_token=token, role=user["role"], username=request.username)

@router.get("/me")
def me(authorization: str = Header(None)):
    from app.auth import authenticate_token
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    sub = authenticate_token(authorization)
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = DEMO_USERS.get(sub, {"role": Role.ANALYST})
    return {"username": sub, "role": user["role"]}
