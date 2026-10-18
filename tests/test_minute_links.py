import tempfile
import unittest
from pathlib import Path

from scripts import update


def match(**changes):
    values = {
        "id": "calendar-uid", "date": "2026-10-18", "time": "11:00",
        "competition": "Primera Division", "home_team": "Cartagines",
        "away_team": "Deportivo Saprissa", "venue": "Fello Meza",
        "source": "unafut", "source_match_id": "2373:396178",
        "live_score_url": "https://www.aiscore.com/match-internal-fallback",
        "last_seen_at": "2026-10-01T00:00:00+00:00",
    }
    values.update(changes)
    return update.Match.from_dict(values)


class MinuteLinkTests(unittest.TestCase):
    def test_today_uses_verified_match_page_without_changing_score_fallback(self):
        game = match()
        update.set_minute_by_minute_links([game])
        self.assertIn("/cs-cartagines-deportivo-saprissa/zGcsUPc", game.minute_by_minute_url)
        self.assertEqual(game.live_score_url, "https://www.aiscore.com/match-internal-fallback")
        self.assertEqual(game.id, "calendar-uid")
        self.assertEqual(game.time, "11:00")

    def test_unmapped_game_uses_sofascore_team_page(self):
        game = match(source_match_id="another-fixture")
        update.set_minute_by_minute_links([game])
        self.assertEqual(game.minute_by_minute_url, update.SOFASCORE_URL)

    def test_link_change_updates_timestamp_once(self):
        game = match()
        old_stamp = game.last_seen_at
        update.set_minute_by_minute_links([game])
        self.assertNotEqual(game.last_seen_at, old_stamp)
        first_stamp = game.last_seen_at
        update.set_minute_by_minute_links([game])
        self.assertEqual(game.last_seen_at, first_stamp)

    def test_calendar_notes_never_show_aiscore(self):
        game = match()
        update.set_minute_by_minute_links([game])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saprissa.ics"
            update.write_ics(path, [game])
            text = path.read_text().replace("\n ", "")
            self.assertIn("Minuto a minuto:", text)
            self.assertIn(game.minute_by_minute_url, text)
            self.assertNotIn("aiscore.com", text)

    def test_primary_source_reconciliation_preserves_public_link(self):
        previous = match()
        update.set_minute_by_minute_links([previous])
        current = match()
        merged, = update.prioritize_competition_matches([current], [previous], [previous.to_dict()])
        update.set_minute_by_minute_links([merged])
        self.assertEqual(merged.minute_by_minute_url, previous.minute_by_minute_url)
        self.assertEqual(merged.last_seen_at, previous.last_seen_at)
