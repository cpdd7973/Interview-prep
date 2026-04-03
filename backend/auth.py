"""
Authentication module — Google OAuth + JWT sessions.
Lightweight: no new dependencies beyond what's already in requirements.txt.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
import httpx

from config import settings
from database import SessionLocal, User

logger = logging.getLogger(__name__)

# --- Constants ---
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
JWT_ALGORITHM = "HS256"

# --- Security scheme ---
bearer_scheme = HTTPBearer(auto_error=False)

# --- Router ---
auth_router = APIRouter(tags=["auth"])


# --- Pydantic Models ---
class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str  # Frontend sends its own redirect_uri for verification


class AuthResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    picture: Optional[str]


# --- JWT Helpers ---
def create_jwt_token(user_id: int, email: str) -> str:
    """Create a signed JWT with user info."""
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# --- Dependency: get_current_user ---
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """
    FastAPI dependency that extracts and validates the JWT from the
    Authorization header and returns the corresponding User object.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = decode_jwt_token(credentials.credentials)
    user_id = int(payload["sub"])

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[User]:
    """
    Same as get_current_user but returns None instead of raising 401.
    Use for endpoints that work with or without auth.
    """
    if not credentials:
        return None
    try:
        payload = decode_jwt_token(credentials.credentials)
        user_id = int(payload["sub"])
        db = SessionLocal()
        try:
            return db.query(User).filter(User.id == user_id).first()
        finally:
            db.close()
    except HTTPException:
        return None


# --- Routes ---
@auth_router.post("/google", response_model=AuthResponse)
async def google_auth(body: GoogleAuthRequest):
    """
    Exchange a Google OAuth authorization code for a JWT session token.
    1. Exchange code for Google tokens
    2. Fetch user info from Google
    3. Upsert user in local DB
    4. Return signed JWT
    """
    # 1. Exchange authorization code for tokens
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": body.code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": body.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if token_resp.status_code != 200:
            logger.error(f"Google token exchange failed: {token_resp.text}")
            raise HTTPException(status_code=401, detail="Google authentication failed")

        tokens = token_resp.json()
        access_token = tokens.get("access_token")

        if not access_token:
            raise HTTPException(status_code=401, detail="No access token from Google")

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during Google token exchange: {e}")
        raise HTTPException(status_code=502, detail="Failed to contact Google")

    # 2. Fetch user info
    try:
        async with httpx.AsyncClient() as client:
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if userinfo_resp.status_code != 200:
            raise HTTPException(
                status_code=401, detail="Failed to fetch Google user info"
            )

        userinfo = userinfo_resp.json()
        email = userinfo.get("email")
        name = userinfo.get("name", email)
        picture = userinfo.get("picture")

        if not email:
            raise HTTPException(status_code=401, detail="Google account has no email")

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching Google user info: {e}")
        raise HTTPException(status_code=502, detail="Failed to contact Google")

    # 3. Upsert user
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            # Update existing user info
            user.name = name
            user.picture = picture
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            logger.info(f"User logged in: {email}")
        else:
            # Create new user
            user = User(email=email, name=name, picture=picture)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"New user registered: {email}")

        # 4. Create JWT
        token = create_jwt_token(user.id, user.email)

        return AuthResponse(
            token=token,
            user={
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture,
            },
        )
    finally:
        db.close()


@auth_router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
    )
