from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from .supabase_client import get_supabase_admin_client


def _unauthorized(detail: str) -> HTTPException:
  return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user_id(
  authorization: str | None = Header(default=None),
) -> str:
  if not authorization or not authorization.startswith("Bearer "):
    raise _unauthorized("Missing bearer token.")

  token = authorization.removeprefix("Bearer ").strip()

  try:
    user_response = get_supabase_admin_client().auth.get_user(token)
  except Exception as error:
    raise _unauthorized("Invalid bearer token.") from error

  user = user_response.user if user_response else None

  if not user or not user.id:
    raise _unauthorized("Token does not map to an authenticated user.")

  return str(user.id)
