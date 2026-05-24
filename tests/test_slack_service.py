"""Tests for region-bucketed Slack sync alerts."""

import json
import unittest
from unittest.mock import patch

from app.services.slack_service import (
    COUNTRY_REGION,
    REGION_OWNERS,
    region_for,
    send_sync_alert,
)


class TestRegionMapping(unittest.TestCase):
    def test_known_countries_resolve(self):
        self.assertEqual(region_for("Germany"), "EMEA")
        self.assertEqual(region_for("India"), "APAC")
        self.assertEqual(region_for("Brazil"), "Americas")

    def test_unknown_country_falls_back_to_emea(self):
        self.assertEqual(region_for("Narnia"), "EMEA")

    def test_all_mapped_countries_have_valid_region(self):
        for country, region in COUNTRY_REGION.items():
            self.assertIn(region, REGION_OWNERS, f"{country} mapped to unknown region {region}")


class TestActionButtons(unittest.TestCase):
    def _capture_payloads(self, sync_result):
        captured = []

        def fake_urlopen(req, timeout=10):
            captured.append(json.loads(req.data.decode()))
            return _FakeResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_sync_alert("https://hooks.example/x", sync_result, triggered_by="manual")
        return captured

    def test_each_message_has_two_action_buttons(self):
        sync_result = {
            "total_changes": 1,
            "endpoints_processed": 1,
            "failures": 0,
            "per_country": {"Germany": {"changes": 1, "failed": False}},
        }
        payloads = self._capture_payloads(sync_result)
        for p in payloads:
            actions = p["attachments"][0]["actions"]
            self.assertEqual(len(actions), 2)
            labels = [a["text"] for a in actions]
            self.assertIn("Review Queue", labels)
            self.assertIn("Open Dashboard", labels)

    def test_buttons_have_urls(self):
        sync_result = {
            "total_changes": 0,
            "endpoints_processed": 0,
            "failures": 0,
            "per_country": {},
        }
        payloads = self._capture_payloads(sync_result)
        for p in payloads:
            for action in p["attachments"][0]["actions"]:
                self.assertTrue(action["url"].startswith("http"))
                self.assertEqual(action["type"], "button")


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class TestSendSyncAlert(unittest.TestCase):
    def _capture_payloads(self, sync_result, triggered_by="manual"):
        captured = []

        def fake_urlopen(req, timeout=10):
            captured.append(json.loads(req.data.decode()))
            return _FakeResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_sync_alert("https://hooks.example/x", sync_result, triggered_by=triggered_by)
        return captured

    def test_posts_one_message_per_region(self):
        sync_result = {
            "total_changes": 2,
            "endpoints_processed": 2,
            "failures": 0,
            "per_country": {
                "Germany": {"changes": 1, "failed": False},
                "India": {"changes": 1, "failed": False},
            },
        }
        payloads = self._capture_payloads(sync_result)
        self.assertEqual(len(payloads), 3)

    def test_region_header_contains_owner(self):
        sync_result = {
            "total_changes": 1,
            "endpoints_processed": 1,
            "failures": 0,
            "per_country": {"Singapore": {"changes": 1, "failed": False}},
        }
        payloads = self._capture_payloads(sync_result)
        texts = [p["attachments"][0]["text"] for p in payloads]
        apac_text = next(t for t in texts if "APAC" in t)
        self.assertIn("Divya", apac_text)
        emea_text = next(t for t in texts if "EMEA" in t)
        self.assertIn("Shweta", emea_text)
        americas_text = next(t for t in texts if "Americas" in t)
        self.assertIn("Kathryn", americas_text)

    def test_country_changes_bucketed_to_correct_region(self):
        sync_result = {
            "total_changes": 5,
            "endpoints_processed": 2,
            "failures": 0,
            "per_country": {
                "Brazil": {"changes": 3, "failed": False},
                "Mexico": {"changes": 2, "failed": False},
            },
        }
        payloads = self._capture_payloads(sync_result)
        texts = [p["attachments"][0]["text"] for p in payloads]
        americas_text = next(t for t in texts if "Americas" in t)
        self.assertIn("Brazil (3)", americas_text)
        self.assertIn("Mexico (2)", americas_text)
        apac_text = next(t for t in texts if "APAC" in t)
        self.assertNotIn("Brazil", apac_text)

    def test_failure_countries_listed(self):
        sync_result = {
            "total_changes": 0,
            "endpoints_processed": 1,
            "failures": 1,
            "per_country": {"Japan": {"changes": 0, "failed": True}},
        }
        payloads = self._capture_payloads(sync_result)
        texts = [p["attachments"][0]["text"] for p in payloads]
        apac_text = next(t for t in texts if "APAC" in t)
        self.assertIn("Failed sources: Japan", apac_text)
        self.assertIn(":warning:", apac_text)

    def test_sync_error_shows_crash_message(self):
        sync_result = {
            "total_changes": 0,
            "endpoints_processed": 0,
            "failures": 1,
            "per_country": {},
            "sync_error": "connection timeout",
        }
        payloads = self._capture_payloads(sync_result)
        for p in payloads:
            text = p["attachments"][0]["text"]
            self.assertIn("crashed", text)
            self.assertIn("connection timeout", text)
            self.assertEqual(p["attachments"][0]["color"], "#d72b3f")

    def test_no_webhook_sends_nothing(self):
        with patch("urllib.request.urlopen") as mock:
            send_sync_alert(None, {"per_country": {}})
            mock.assert_not_called()

    def test_empty_per_country_sends_quiet_alerts(self):
        sync_result = {
            "total_changes": 0,
            "endpoints_processed": 0,
            "failures": 0,
            "per_country": {},
        }
        payloads = self._capture_payloads(sync_result)
        self.assertEqual(len(payloads), 3)
        for p in payloads:
            text = p["attachments"][0]["text"]
            self.assertIn("Changes queued for review: *0*", text)
            self.assertEqual(p["attachments"][0]["color"], "#aaaaaa")


if __name__ == "__main__":
    unittest.main()
