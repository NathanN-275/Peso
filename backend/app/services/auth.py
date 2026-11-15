from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status

from .config import get_settings
from .supabase_client import get_supabase_admin_client


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedAuthContext:
  user_id: str
  session_id: str
  expires_at: int


def _unauthorized(detail: str) -> HTTPException:
  return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _verify_bearer_user(authorization: str | None) -> tuple[str, str]:
  if not authorization or not authorization.startswith("Bearer "):
    logger.warning("Rejected authenticated request because bearer token is missing.")
    raise _unauthorized("Missing bearer token.")

  token = authorization.removeprefix("Bearer ").strip()

  try:
    user_response = get_supabase_admin_client().auth.get_user(token)
  except Exception as error:
    logger.warning("Rejected authenticated request because bearer token could not be verified.")
    raise _unauthorized("Invalid bearer token.") from error

  user = user_response.user if user_response else None

  if not user or not user.id:
    logger.warning("Rejected authenticated request because token did not map to a user.")
    raise _unauthorized("Token does not map to an authenticated user.")

  return str(user.id), token


def get_current_user_id(
  authorization: str | None = Header(default=None),
) -> str:
  user_id, _ = _verify_bearer_user(authorization)
  return user_id


def get_current_auth_context(
  authorization: str | None = Header(default=None),
) -> VerifiedAuthContext:
  # Decode only after Auth verified this exact token; live-session checks remain separate.
  user_id, token = _verify_bearer_user(authorization)
  try:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
      raise ValueError
    encoded = parts[1]
    payload = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii") != encoded:
      raise ValueError
    claims = json.loads(payload)
    if not isinstance(claims, dict) or claims.get("sub") != user_id:
      raise ValueError
    parsed_user = UUID(user_id)
    if not parsed_user.int or str(parsed_user) != user_id:
      raise ValueError
    project_url = get_settings().supabase_url.rstrip("/")
    if not project_url or claims.get("iss") != project_url + "/auth/v1":
      raise ValueError
    audience = claims.get("aud")
    if audience != "authenticated" and audience != ["authenticated"]:
      raise ValueError
    if claims.get("role") != "authenticated":
      raise ValueError
    session_id = claims.get("session_id")
    if not isinstance(session_id, str):
      raise ValueError
    parsed_session = UUID(session_id)
    if not parsed_session.int or str(parsed_session) != session_id:
      raise ValueError
    expires_at = claims.get("exp")
    if type(expires_at) is not int or expires_at <= time.time():
      raise ValueError
  except (ValueError, TypeError, UnicodeError, binascii.Error):
    logger.warning("Rejected authenticated request because verified token claims are invalid.")
    raise _unauthorized("Invalid bearer token claims.") from None

  return VerifiedAuthContext(user_id=user_id, session_id=session_id, expires_at=expires_at)
