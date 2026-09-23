import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from public_beta_budget_policy import ChargeSample, evaluate, undelivered_milestones


NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


def samples(actual="0.00", projected="0.00", month="2026-09"):
    return [ChargeSample(provider, month, NOW, Decimal(actual), Decimal(projected))
            for provider in ("render", "supabase", "netlify")]


class BudgetPolicyTests(unittest.TestCase):
    def test_exact_projected_stop_preserves_separate_actual_alerts(self):
        readings = samples("0.00", "0.00")
        readings[0] = replace(readings[0], actual_usd=Decimal("14.99"), projected_usd=Decimal("50.00"))
        decision = evaluate(readings, now=NOW)
        self.assertTrue(decision.stop_new_uploads)
        self.assertEqual(decision.reached_milestones, ())

    def test_crossed_thresholds_and_monthly_delivery_keys(self):
        readings = samples()
        readings[0] = replace(readings[0], actual_usd=Decimal("35.00"), projected_usd=Decimal("36.00"))
        decision = evaluate(readings, now=NOW)
        self.assertEqual(undelivered_milestones(decision, {("2026-09", 15), ("2026-08", 25)}), (25, 35))
        self.assertFalse(decision.stop_new_uploads)

    def test_rejects_missing_stale_or_misaligned_provider_data(self):
        for invalid in (
            samples()[:2],
            [replace(item, observed_at=NOW - timedelta(minutes=6)) for item in samples()],
            samples(month="2026-08"),
            [replace(item, projected_usd=Decimal("NaN")) for item in samples()],
            [replace(item, actual_usd=Decimal("1.001"), projected_usd=Decimal("2")) for item in samples()],
            [replace(item, actual_usd=None) for item in samples()],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evaluate(invalid, now=NOW)


if __name__ == "__main__":
    unittest.main()
