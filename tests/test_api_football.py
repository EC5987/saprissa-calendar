import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.api_football import ApiFootballClient, ApiFootballError, check_access


class ApiFootballTests(unittest.TestCase):
    def test_missing_key_fails_before_request(self):
        with patch("scripts.api_football.urlopen") as request:
            with self.assertRaises(ApiFootballError):
                ApiFootballClient("")
            request.assert_not_called()

    def test_key_is_in_header_only(self):
        with patch("scripts.api_football.urlopen") as request:
            request.return_value.__enter__.return_value = io.StringIO(json.dumps({"errors": [], "response": []}))
            ApiFootballClient("example-secret").get("teams", search="saprissa")
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_header("X-apisports-key"), "example-secret")
            self.assertNotIn("example-secret", sent.full_url)

    def test_http_200_plan_errors_are_reported_and_redacted(self):
        with patch("scripts.api_football.urlopen") as request:
            request.return_value.__enter__.return_value = io.StringIO(json.dumps({
                "errors": {"plan": "Season 2026 is unavailable for example-secret"}, "response": []
            }))
            with self.assertRaises(ApiFootballError) as raised:
                ApiFootballClient("example-secret").get("fixtures", team=123, season=2026)
            self.assertIn("Season 2026 is unavailable", str(raised.exception))
            self.assertNotIn("example-secret", str(raised.exception))

    def test_incomplete_fixture_list_is_rejected(self):
        with patch("scripts.api_football.urlopen") as request:
            request.return_value.__enter__.return_value = io.StringIO(json.dumps({
                "errors": [], "response": [], "paging": {"current": 1, "total": 2}
            }))
            with self.assertRaises(ApiFootballError):
                ApiFootballClient("example-secret").get("fixtures", team=123, season=2026)

    def test_utc_time_is_converted_and_live_score_is_not_printed(self):
        fixture = {
            "fixture": {"id": 456, "date": "2026-10-18T17:00:00+00:00", "status": {"short": "1H"}},
            "league": {"name": "Primera Division"},
            "teams": {"home": {"id": 789, "name": "Cartagines"}, "away": {"id": 123, "name": "Saprissa"}},
            "goals": {"home": 2, "away": 1},
        }
        with patch.object(ApiFootballClient, "get", side_effect=[
            [{"team": {"id": 123, "country": "Costa-Rica", "name": "Saprissa"}}], [fixture]
        ]), redirect_stdout(io.StringIO()) as output:
            check_access("example-secret", 2026)
        self.assertIn("2026-10-18 11:00", output.getvalue())
        self.assertNotIn("2-1", output.getvalue())
        self.assertNotIn("example-secret", output.getvalue())
