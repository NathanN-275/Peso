from __future__ import annotations

import base64
from dataclasses import asdict, FrozenInstanceError
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from app.services.auth import get_current_auth_context, get_current_user_id, VerifiedAuthContext


USER_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
NOW = 1792950000
SUPABASE_URL = "https://project-fixture.supabase.co"
ISSUER = SUPABASE_URL + "/auth/v1"


def encode(value: bytes) -> str:
  return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def token(claims=None, *, payload: bytes | None = None) -> str:
  if claims is None:
    claims = {"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 300}
  claims = {"iss": ISSUER, "aud": "authenticated", "role": "authenticated", **claims}
  body = payload if payload is not None else json.dumps(claims).encode()
  return encode(b'{"alg":"HS256","typ":"JWT"}') + "." + encode(body) + ".synthetic_signature"


class VerifiedAuthContextTest(unittest.TestCase):
  def setUp(self):
    self.client = MagicMock()
    self.client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id=USER_ID))
    self.admin = patch("app.services.auth.get_supabase_admin_client", return_value=self.client)
    self.admin.start()
    self.addCleanup(self.admin.stop)
    self.clock = patch("app.services.auth.time.time", return_value=NOW)
    self.clock.start()
    self.addCleanup(self.clock.stop)
    self.settings = patch("app.services.auth.get_settings", return_value=SimpleNamespace(supabase_url=SUPABASE_URL))
    self.settings.start()
    self.addCleanup(self.settings.stop)

  def reject(self, raw_token):
    with self.assertRaises(HTTPException) as raised:
      get_current_auth_context("Bearer " + raw_token)
    self.assertEqual(raised.exception.status_code, 401)
    return raised.exception

  def test_valid_context_has_only_verified_identity_session_and_expiry(self):
    raw_token = token()
    context = get_current_auth_context("Bearer " + raw_token)
    self.assertEqual(context, VerifiedAuthContext(USER_ID, SESSION_ID, NOW + 300))
    self.assertEqual(asdict(context), {"user_id": USER_ID, "session_id": SESSION_ID, "expires_at": NOW + 300})
    self.assertNotIn(raw_token, repr(context))
    self.client.auth.get_user.assert_called_once_with(raw_token)
    with self.assertRaises(FrozenInstanceError):
      context.session_id = "changed"

  def test_provider_verification_completes_before_payload_decoding(self):
    events = []
    real_loads = json.loads
    self.client.auth.get_user.side_effect = lambda value: events.append("verified") or SimpleNamespace(user=SimpleNamespace(id=USER_ID))
    with patch("app.services.auth.json.loads", side_effect=lambda value: events.append("decoded") or real_loads(value)):
      get_current_auth_context("Bearer " + token())
    self.assertEqual(events, ["verified", "decoded"])

  def test_provider_failure_does_not_decode_claims_or_log_credentials(self):
    raw_token = token({"sub": USER_ID, "session_id": "synthetic-secret", "exp": NOW + 300})
    self.client.auth.get_user.side_effect = RuntimeError("provider echoed " + raw_token)
    with patch("app.services.auth.json.loads") as decode, self.assertLogs("app.services.auth", level="WARNING") as logs:
      error = self.reject(raw_token)
    decode.assert_not_called()
    self.assertNotIn(raw_token, " ".join(logs.output) + error.detail)
    self.assertEqual(error.detail, "Invalid bearer token.")

  def test_unknown_user_does_not_decode_claims(self):
    for response in (None, SimpleNamespace(user=None), SimpleNamespace(user=SimpleNamespace(id=""))):
      with self.subTest(response=response), patch("app.services.auth.json.loads") as decode:
        self.client.auth.get_user.return_value = response
        self.reject(token())
        decode.assert_not_called()

  def test_missing_bearer_preserves_errors_and_skips_provider(self):
    for value in (None, "", "Basic synthetic", "bearer synthetic"):
      for authenticate in (get_current_auth_context, get_current_user_id):
        with self.subTest(value=value, authenticate=authenticate), self.assertRaises(HTTPException) as raised:
          authenticate(value)
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Missing bearer token.")
    self.client.auth.get_user.assert_not_called()

  def test_subject_must_be_present_and_match_verified_user(self):
    for subject in (None, "", "another-user", 12, True, [USER_ID]):
      with self.subTest(subject=subject):
        self.reject(token({"sub": subject, "session_id": SESSION_ID, "exp": NOW + 300}))
    self.reject(token({"session_id": SESSION_ID, "exp": NOW + 300}))

  def test_matching_provider_subject_must_still_be_a_canonical_nonnil_uuid(self):
    for subject in ("00000000-0000-0000-0000-000000000000", "legacy-user", "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE", USER_ID.replace("-", "")):
      with self.subTest(subject=subject):
        self.client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id=subject))
        self.reject(token({"sub": subject, "session_id": SESSION_ID, "exp": NOW + 300}))

  def test_issuer_must_exactly_match_the_configured_project(self):
    for issuer in (None, "", "supabase", "https://other.supabase.co/auth/v1", ISSUER + "/", SUPABASE_URL,
                   "http://project-fixture.supabase.co/auth/v1", [ISSUER], True):
      with self.subTest(issuer=issuer):
        self.reject(token({"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 300, "iss": issuer}))
    with patch("app.services.auth.get_settings", return_value=SimpleNamespace(supabase_url=SUPABASE_URL + "/")):
      self.assertEqual(get_current_auth_context("Bearer " + token()).user_id, USER_ID)
    with patch("app.services.auth.get_settings", return_value=SimpleNamespace(supabase_url="")):
      self.reject(token())

  def test_audience_is_authenticated_string_or_singleton_list_only(self):
    for audience in ("authenticated", ["authenticated"]):
      with self.subTest(audience=audience):
        self.assertEqual(get_current_auth_context("Bearer " + token({"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 300, "aud": audience})).user_id, USER_ID)
    for audience in (None, "", "anon", "service_role", "Authenticated", [], ["anon"], ["authenticated", "anon"],
                     ["authenticated", "authenticated"], {"aud": "authenticated"}, True, 1, [True]):
      with self.subTest(audience=audience):
        self.reject(token({"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 300, "aud": audience}))

  def test_role_requires_the_authenticated_string(self):
    for role in (None, "", "anon", "service_role", "Authenticated", ["authenticated"], {"role": "authenticated"}, True, 1):
      with self.subTest(role=role):
        self.reject(token({"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 300, "role": role}))

  def test_issuer_audience_and_role_cannot_be_omitted(self):
    complete = {"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 300, "iss": ISSUER,
                "aud": "authenticated", "role": "authenticated"}
    for name in ("iss", "aud", "role"):
      with self.subTest(name=name):
        claims = dict(complete)
        claims.pop(name)
        self.reject(token(payload=json.dumps(claims).encode()))

  def test_session_id_requires_nonzero_canonical_uuid(self):
    for session in (None, "", "not-a-uuid", SESSION_ID.upper(), SESSION_ID.replace("-", ""),
                    "00000000-0000-0000-0000-000000000000", " " + SESSION_ID, 1, True, [SESSION_ID]):
      with self.subTest(session=session):
        self.reject(token({"sub": USER_ID, "session_id": session, "exp": NOW + 300}))
    self.reject(token({"sub": USER_ID, "exp": NOW + 300}))

  def test_expiry_requires_future_integer_and_denies_exact_boundary(self):
    for expiry in (None, 0, -1, NOW, NOW - 1, True, False, str(NOW + 300), NOW + 0.5,
                   float("nan"), float("inf"), float("-inf"), [NOW + 300]):
      with self.subTest(expiry=expiry):
        self.reject(token({"sub": USER_ID, "session_id": SESSION_ID, "exp": expiry}))
    self.reject(token({"sub": USER_ID, "session_id": SESSION_ID}))
    self.assertEqual(get_current_auth_context("Bearer " + token({"sub": USER_ID, "session_id": SESSION_ID, "exp": NOW + 1})).expires_at, NOW + 1)

  def test_malformed_jwt_and_payload_are_rejected_after_provider_verifies(self):
    for value in ("legacy-token", "one.two", "one..three", ".two.three", "one.two.", "one.two.three.four",
                  "one.%%%%.three", "one." + encode(b"\xff") + ".three", token(payload=b"not json"),
                  token(payload=b"[]"), token(payload=b"null"), token(payload=b"1"),
                  "one." + encode(b"{}") + "=.three"):
      with self.subTest(value=value):
        self.reject(value)
    self.assertGreater(self.client.auth.get_user.call_count, 0)

  def test_claim_rejection_does_not_log_or_return_payload_values(self):
    secret = "synthetic-private-session"
    raw_token = token({"sub": USER_ID, "session_id": secret, "exp": NOW + 300})
    with self.assertLogs("app.services.auth", level="WARNING") as logs:
      error = self.reject(raw_token)
    self.assertNotIn(secret, " ".join(logs.output) + error.detail)
    self.assertNotIn(raw_token, " ".join(logs.output) + error.detail)
    self.assertIsNone(error.__cause__)

  def test_legacy_user_id_validation_does_not_require_new_context_claims(self):
    self.assertEqual(get_current_user_id("Bearer   legacy-token  "), USER_ID)
    self.client.auth.get_user.assert_called_once_with("legacy-token")
    self.reject("legacy-token")

  def test_existing_fastapi_dependency_identity_and_header_behavior_remain(self):
    app = FastAPI()
    @app.get("/legacy")
    def legacy(user_id: str = Depends(get_current_user_id)):
      return {"user_id": user_id}
    @app.get("/context")
    def context(value: VerifiedAuthContext = Depends(get_current_auth_context)):
      return asdict(value)
    client = TestClient(app)
    self.assertEqual(client.get("/legacy", headers={"Authorization": "Bearer legacy-token"}).json(), {"user_id": USER_ID})
    self.assertEqual(client.get("/context", headers={"Authorization": "Bearer " + token()}).json()["session_id"], SESSION_ID)
    app.dependency_overrides[get_current_user_id] = lambda: "override-user"
    self.assertEqual(client.get("/legacy").json(), {"user_id": "override-user"})
    self.assertEqual(client.get("/context").status_code, 401)


if __name__ == "__main__":
  unittest.main()
