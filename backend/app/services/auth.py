from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from .config import Settings, get_settings


def _unauthorized(detail: str) -> HTTPException:
  return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user_id(
  authorization: str | None = Header(default=None),
  settings: Settings = Depends(get_settings),
) -> str:
  if not authorization or not authorization.startswith("Bearer "):
    raise _unauthorized("Missing bearer token.")

  token = authorization.removeprefix("Bearer ").strip()

  try:
    payload: dict[str, Any] = jwt.decode(
      token,
      settings.supabase_jwt_secret,
      algorithms=["HS256"],
      options={"verify_aud": False},
    )
  except JWTError as error:
    raise _unauthorized("Invalid bearer token.") from error

  user_id = payload.get("sub")
  role = payload.get("role")

  if not user_id or role not in {"authenticated", "service_role"}:
    raise _unauthorized("Token does not map to an authenticated user.")

  return str(user_id)
