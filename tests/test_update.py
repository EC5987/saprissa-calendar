import argparse
import html
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update


def card(home="Deportivo Saprissa", away="L.A. Firpo", *, date="Wednesday 28 de October , 2026 - 6:30 pm", scores=(None, None)):
    score_html = "".join(
        f'<div class="game-card_score_item"><div>{score if score is not None else ""}</div>'
        '<div class="w-condition-invisible">--</div></div>'
        for score in scores
    )
    return (
        '<a class="game-card w-inline-block" href="/partidos/test-match">'
        f'<div class="game-card_date">{html.escape(date)}</div>'
        '<div class="game-card_type"><div>Primera Divisi\u00f3n - </div><div>Torneo de Apertura</div></div>'
        f'<div class="team-name is-left">{html.escape(home)}</div><img src="home.png"/>'
        f'<div class="game-card_score">{score_html}</div>'
        f'<img src="away.png"><div class="team-name is-right">{html.escape(away)}</div>'
        '<div class="game-card_bottom"><div>Ricardo Saprissa</div></div>'
        '<div class="live-pill w-condition-invisible">Live</div></a>'
    )


class OfficialParserTests(unittest.TestCase):
    def test_unknown_opponents_in_both_positions(self):
        for home, away in [
            ("Escorpiones de Bel\u00e9n", "Deportivo Saprissa"),
            ("L.A. Firpo", "Deportivo Saprissa"),
            ("Deportivo Saprissa", "L.A. Firpo"),
            ("Deportivo Saprissa", "New Opponent FC"),
        ]:
            with self.subTest(home=home, away=away):
                match, = update.parse_official_schedule(card(home, away))
                self.assertEqual((match.home_team, match.away_team), (home, away))
                self.assertEqual(match.time, "18:30")
                self.assertEqual(match.venue, "Ricardo Saprissa")
                self.assertEqual(match.competition, "Primera Divisi\u00f3n - Torneo de Apertura")
                self.assertIsNone(match.home_score)

    def test_official_final_score_including_zero(self):
        match, = update.parse_official_results(card(scores=(2, 0)))
        self.assertEqual((match.status, match.home_score, match.away_score), ("final", 2, 0))

    def test_womens_matches_and_previous_season_are_excluded(self):
        self.assertEqual(update.parse_official_schedule(card(away="Deportivo Saprissa (FF)")), [])
        self.assertEqual(update.parse_official_results(card(date="Sunday 1 de June , 2026 - 4:00 pm", scores=(1, 0))), [])

    def test_unknown_time(self):
        match, = update.parse_official_schedule(card(date="Sunday 11 de October , 2026 - Por confirmar"))
        self.assertTrue(match.is_time_tbd)
        self.assertIsNone(match.time)

    def test_unreadable_cards_fail_even_with_valid_cards(self):
        for malformed in [
            card(away=""),
            card(date="Unknown date"),
            card().replace('class="team-name is-right"', 'class="changed-team-field"'),
        ]:
            with self.subTest(malformed=malformed):
                with self.assertRaises(update.OfficialParseError):
                    update.parse_official_schedule(card() + malformed)

    def test_empty_or_truncated_pages_fail(self):
        for page in ["<html>Maintenance</html>", card().removesuffix("</a>")]:
            with self.subTest(page=page):
                with self.assertRaises(update.OfficialParseError):
                    update.parse_official_schedule(page)

    def test_results_without_final_score_fail(self):
        with self.assertRaises(update.OfficialParseError):
            update.parse_official_results(card(scores=(2, None)))

    def test_team_rename_preserves_event_id_without_duplicate(self):
        old, = update.parse_official_results(card(away="Escorpiones", scores=(2, 1)))
        old.last_seen_at = "2026-08-30T06:00:00+00:00"
        old.live_score_url = "https://www.aiscore.com/match-example"
        new, = update.parse_official_results(card(away="Escorpiones de Bel\u00e9n", scores=(2, 1)))
        update.preserve_existing_metadata([new], [old.to_dict()])
        self.assertEqual(new.id, old.id)
        self.assertEqual(new.live_score_url, old.live_score_url)
        self.assertNotEqual(new.last_seen_at, old.last_seen_at)
        merged = update.merge_matches([new], [], [old.to_dict()], prune_stale_future=True)
        self.assertEqual(len(merged), 1)

    def test_unchanged_data_keeps_timestamp(self):
        old, = update.parse_official_schedule(card())
        old.last_seen_at = "2026-08-30T06:00:00+00:00"
        new, = update.parse_official_schedule(card())
        update.preserve_existing_metadata([new], [old.to_dict()])
        self.assertEqual(new.last_seen_at, old.last_seen_at)

    def test_parse_failure_leaves_existing_files_untouched(self):
        for failed_source in [update.OFFICIAL_URL, update.RESULTS_URL]:
            with self.subTest(source=failed_source), tempfile.TemporaryDirectory() as directory:
                data_path = Path(directory) / "matches.json"
                ics_path = Path(directory) / "saprissa.ics"
                data_path.write_text("[]\n")
                ics_path.write_text("existing feed")
                args = argparse.Namespace(data_file=str(data_path), ics_file=str(ics_path), no_aiscore=True)
                def fetch(url):
                    return "<html>Changed layout</html>" if url == failed_source else card()
                with patch.object(update, "fetch", side_effect=fetch):
                    self.assertEqual(update.run(args), 1)
                self.assertEqual(data_path.read_text(), "[]\n")
                self.assertEqual(ics_path.read_text(), "existing feed")


if __name__ == "__main__":
    unittest.main()
