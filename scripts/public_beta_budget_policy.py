"""Provider-neutral decision rules for the Peso public beta spending guardrail.

Billing adapters must supply USD calendar-month totals from authoritative sources.
This module does not infer charges from usage counters or send notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re


PROVIDERS = frozenset({"render", "supabase", "netlify"})
MILESTONES = (15, 25, 35, 50)
STOP_AT = Decimal("50.00")
MAX_SAMPLE_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class ChargeSample:
    provider: str
    month: str
    observed_at: datetime
    actual_usd: Decimal
    projected_usd: Decimal


@dataclass(frozen=True)
class BudgetDecision:
    month: str
    actual_usd: Decimal
    projected_usd: Decimal
    reached_milestones: tuple[int, ...]
    stop_new_uploads: bool


def _dollars(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("A charge must be a nonnegative USD amount.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("A charge must be a nonnegative USD amount.") from error
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError("A charge must be a finite, nonnegative USD cent amount.")
    return amount


def evaluate(samples: list[ChargeSample], *, now: datetime | None = None) -> BudgetDecision:
    """Require one current, calendar-aligned sample for every cost provider."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The evaluation time must include a timezone.")
    month = now.astimezone(timezone.utc).strftime("%Y-%m")
    if len(samples) != len(PROVIDERS) or {sample.provider for sample in samples} != PROVIDERS:
        raise ValueError("Current charges are required from Render, Supabase, and Netlify.")
    actual = Decimal("0.00")
    projected = Decimal("0.00")
    for sample in samples:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", sample.month) or sample.month != month:
            raise ValueError("Provider charges must use the current UTC calendar month.")
        if sample.observed_at.tzinfo is None or sample.observed_at.utcoffset() is None:
            raise ValueError("Provider observations must include a timezone.")
        age = (now - sample.observed_at).total_seconds()
        if age < -30 or age > MAX_SAMPLE_AGE_SECONDS:
            raise ValueError("A provider observation is stale or in the future.")
        actual_charge = _dollars(sample.actual_usd)
        projected_charge = _dollars(sample.projected_usd)
        if projected_charge < actual_charge:
            raise ValueError("A provider projection cannot omit charges already incurred.")
        actual += actual_charge
        projected += projected_charge
    return BudgetDecision(
        month=month,
        actual_usd=actual,
        projected_usd=projected,
        reached_milestones=tuple(value for value in MILESTONES if actual >= value),
        stop_new_uploads=projected >= STOP_AT,
    )


def undelivered_milestones(decision: BudgetDecision, delivered: set[tuple[str, int]]) -> tuple[int, ...]:
    """Select each reached threshold not yet delivered in this calendar month."""
    return tuple(value for value in decision.reached_milestones if (decision.month, value) not in delivered)
