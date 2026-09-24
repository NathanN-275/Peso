import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from run_public_beta_budget_monitor import main, parse_provider, process


NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


def entry(actual="0.00", projected="0.00", checked_at=NOW, month="2026-09"):
    return json.dumps({
        "month": month,
        "period_start": f"{month}-01",
        "period_end_exclusive": "2026-10-01" if month == "2026-09" else "2026-09-01",
        "checked_at": checked_at.isoformat(),
        "source_reference": "Provider dashboard calendar-month detail, checked by Nathan",
        "actual_usd": actual,
        "projected_usd": projected,
    })


class FakeRpc:
    def __init__(self):
        self.calls = []
        self.claimed = set()

    def __call__(self, name, values):
        self.calls.append((name, values))
        if name == "claim_budget_alert":
            key = (values["p_month_start"], values["p_threshold_usd"])
            if key in self.claimed:
                return False
            self.claimed.add(key)
            return True
        if name in ("complete_budget_alert", "release_budget_alert"):
            if name == "release_budget_alert":
                self.claimed.discard((values["p_month_start"], values["p_threshold_usd"]))
            return True
        return None


class MonitorTests(unittest.TestCase):
    def test_exact_budget_stop_and_multiple_alerts_are_deduplicated(self):
        rpc = FakeRpc()
        sent = []
        entries = {"render": entry("35.00", "50.00"),
                   "supabase": entry(), "netlify": entry()}
        first = process(entries, rpc, lambda threshold, month, decision: sent.append(threshold), now=NOW)
        second = process(entries, rpc, lambda threshold, month, decision: sent.append(threshold), now=NOW)
        self.assertEqual(first, ("paused_projected_budget", (15, 25, 35)))
        self.assertEqual(second, ("paused_projected_budget", ()))
        self.assertEqual(sent, [15, 25, 35])
        self.assertEqual(sum(name == "disable_video_upload_admission" for name, _ in rpc.calls), 2)

    def test_missing_stale_or_cross_cycle_figures_stop_intake_before_email(self):
        for entries in (
            {"render": entry(), "supabase": entry()},
            {"render": entry(checked_at=NOW - timedelta(days=1, seconds=1)),
             "supabase": entry(), "netlify": entry()},
            {"render": entry(), "supabase": entry(month="2026-08"), "netlify": entry()},
        ):
            with self.subTest(entries=entries):
                rpc = FakeRpc()
                sent = []
                self.assertEqual(process(entries, rpc, lambda *args: sent.append(args), now=NOW),
                                 ("paused_missing_cost_data", ()))
                self.assertEqual([name for name, _ in rpc.calls], ["disable_video_upload_admission"])
                self.assertEqual(sent, [])

    def test_failed_email_releases_claim_for_retry(self):
        rpc = FakeRpc()
        entries = {"render": entry("15.00", "20.00"),
                   "supabase": entry(), "netlify": entry()}
        with self.assertRaisesRegex(RuntimeError, "email delivery failed"):
            process(entries, rpc, lambda *args: (_ for _ in ()).throw(OSError("SMTP down")), now=NOW)
        sent = []
        self.assertEqual(process(entries, rpc, lambda amount, *_: sent.append(amount), now=NOW),
                         ("measured", (15,)))
        self.assertEqual(sent, [15])

    def test_entry_rejects_billing_cycle_total_as_calendar_month(self):
        value = json.loads(entry())
        value["period_start"] = "2026-09-04"
        with self.assertRaisesRegex(ValueError, "calendar month"):
            parse_provider("netlify", json.dumps(value))

    def test_malformed_entries_fail_closed(self):
        for replacement in ({"month": "2026-09-32"}, {"checked_at": None}, {"actual_usd": "not a price"}):
            with self.subTest(replacement=replacement):
                bad = json.loads(entry())
                bad.update(replacement)
                rpc = FakeRpc()
                entries = {provider: entry() for provider in ("render", "supabase", "netlify")}
                entries["render"] = json.dumps(bad)
                self.assertEqual(process(entries, rpc, lambda *args: self.fail("email sent"), now=NOW),
                                 ("paused_missing_cost_data", ()))
                self.assertEqual([name for name, _ in rpc.calls], ["disable_video_upload_admission"])

    def test_invalid_email_configuration_stops_intake(self):
        rpc = FakeRpc()
        with patch.dict(os.environ, {
            "PESO_BUDGET_SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "PESO_BUDGET_EMAIL_ADDRESS": "invalid-address",
            "PESO_BUDGET_GMAIL_APP_PASSWORD": "test-app-password",
        }), patch("run_public_beta_budget_monitor.SupabaseBudgetRpc", return_value=rpc):
            self.assertEqual(main(), 1)
        self.assertEqual([name for name, _ in rpc.calls], ["disable_video_upload_admission"])


if __name__ == "__main__":
    unittest.main()
