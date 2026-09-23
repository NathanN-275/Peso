"""Hourly, fail-closed public beta intake and email monitor.

Each provider's JSON secret is entered from a verified calendar-month billing
view. Never print its contents, provider credentials, or API response bodies.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import sys
from datetime import date, datetime, timezone
from email.message import EmailMessage
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from public_beta_budget_policy import ChargeSample, evaluate


SUPABASE_ORIGIN = "https://jfgiydtrskpqxyorvvbc.supabase.co"
SECRET_NAMES = {
    "render": "PESO_RENDER_BILLING_JSON",
    "supabase": "PESO_SUPABASE_BILLING_JSON",
    "netlify": "PESO_NETLIFY_BILLING_JSON",
}


def _next_month(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    return f"{year + (number == 12):04d}-{1 if number == 12 else number + 1:02d}-01"


def parse_provider(provider: str, raw: str) -> ChargeSample:
    """Reject incomplete or cross-cycle entries before any spending decision."""
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {
        "month", "period_start", "period_end_exclusive", "checked_at",
        "source_reference", "actual_usd", "projected_usd",
    }:
        raise ValueError("Billing entry has missing or unexpected fields.")
    month = data["month"]
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or data["period_start"] != f"{month}-01":
        raise ValueError("Billing entry must cover one UTC calendar month.")
    if data["period_end_exclusive"] != _next_month(month):
        raise ValueError("Billing entry must cover one UTC calendar month.")
    reference = data["source_reference"]
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 300:
        raise ValueError("Billing entry must cite its verified source.")
    if not isinstance(data["checked_at"], str):
        raise ValueError("Billing entry must include a timestamp.")
    checked = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
    return ChargeSample(provider, month, checked, data["actual_usd"], data["projected_usd"])


class SupabaseBudgetRpc:
    def __init__(self, service_key: str):
        if not service_key:
            raise ValueError("The PesoDatabase service credential is missing.")
        self.service_key = service_key

    def __call__(self, name: str, values: dict[str, object]) -> object:
        request = Request(
            f"{SUPABASE_ORIGIN}/rest/v1/rpc/{name}",
            data=json.dumps(values).encode("utf-8"),
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read(2048)
                return json.loads(body) if body else None
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError(f"PesoDatabase RPC {name} did not succeed.") from error


def gmail_sender(address: str, app_password: str) -> Callable[[int, str, object], None]:
    if not address or "@" not in address or not app_password:
        raise ValueError("Gmail delivery credentials are missing.")

    def send(threshold: int, month: str, decision: object) -> None:
        message = EmailMessage()
        message["From"] = address
        message["To"] = address
        message["Subject"] = f"Peso budget: ${threshold} actual spending reached in {month}"
        message.set_content(
            f"Combined actual spending: ${decision.actual_usd:.2f}\n"
            f"Projected calendar-month spending: ${decision.projected_usd:.2f}\n"
            "New uploads stop automatically when projected spending reaches $50.\n"
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(address, app_password)
            smtp.send_message(message)

    return send


def process(
    entries: dict[str, str],
    rpc: Callable[[str, dict[str, object]], object],
    send: Callable[[int, str, object], None],
    *,
    now: datetime | None = None,
) -> tuple[str, tuple[int, ...]]:
    now = now or datetime.now(timezone.utc)
    try:
        decision = evaluate([parse_provider(provider, entries.get(provider, ""))
                             for provider in SECRET_NAMES], now=now)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        rpc("disable_video_upload_admission", {})
        return "paused_missing_cost_data", ()

    if decision.stop_new_uploads:
        rpc("disable_video_upload_admission", {})
    month_start = date.fromisoformat(f"{decision.month}-01").isoformat()
    delivered = []
    for threshold in decision.reached_milestones:
        claim_id = str(uuid4())
        claim = {"p_month_start": month_start, "p_threshold_usd": threshold, "p_claim_id": claim_id}
        if rpc("claim_budget_alert", claim) is not True:
            continue
        try:
            send(threshold, decision.month, decision)
        except Exception:
            rpc("release_budget_alert", claim)
            raise RuntimeError("Budget alert email delivery failed.") from None
        if rpc("complete_budget_alert", claim) is not True:
            raise RuntimeError("Budget alert delivery could not be acknowledged.")
        delivered.append(threshold)
    return ("paused_projected_budget" if decision.stop_new_uploads else "measured"), tuple(delivered)


def main() -> int:
    try:
        rpc = SupabaseBudgetRpc(os.getenv("PESO_BUDGET_SUPABASE_SERVICE_ROLE_KEY", ""))
        address = os.getenv("PESO_BUDGET_EMAIL_ADDRESS", "")
        password = os.getenv("PESO_BUDGET_GMAIL_APP_PASSWORD", "")
        if not address or "@" not in address or not password:
            rpc("disable_video_upload_admission", {})
            raise RuntimeError("The budget alert sender is unavailable.")
        entries = {provider: os.getenv(name, "") for provider, name in SECRET_NAMES.items()}
        result, delivered = process(
            entries, rpc,
            gmail_sender(address, password),
        )
    except Exception:
        print("Budget monitor failed; verify intake state and private workflow configuration.", file=sys.stderr)
        return 1
    print(f"Budget monitor state: {result}; newly delivered threshold count: {len(delivered)}")
    return 0 if result != "paused_missing_cost_data" else 1


if __name__ == "__main__":
    raise SystemExit(main())
