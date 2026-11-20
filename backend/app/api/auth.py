"""Protected endpoints for the Supabase-authenticated identity."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.security.supabase_jwt import (
    SupabaseConfigurationError,
    SupabaseIdentity,
    SupabaseJWKSUnavailable,
    SupabaseTokenInvalid,
    get_supabase_verifier,
)


router = APIRouter(prefix="/users", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


class UserProfile(BaseModel):
    id: str
    email: str | None = None


def require_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> SupabaseIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return get_supabase_verifier().verify(credentials.credentials)
    except SupabaseConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured.",
        ) from exc
    except SupabaseJWKSUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is temporarily unavailable.",
        ) from exc
    except SupabaseTokenInvalid as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get("/me", response_model=UserProfile)
def get_current_profile(
    user: Annotated[SupabaseIdentity, Depends(require_authenticated_user)],
) -> UserProfile:
    return UserProfile(id=user.subject, email=user.email)
