import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import official_sources as sources, update


TEAM = "concacaf::Football_Team::saprissa"


def unafut_row(**changes):
    row = {
        "matchId": 396204, "matchStatus": "SCHEDULED", "matchTimeUTC": "2026-11-06 02:00:00",
        "competitors": [
            {"competitorId": 14078, "competitorName": "C.S. Herediano", "scoreString": "0"},
            {"competitorId": 14044, "competitorName": "Deportivo Saprissa", "scoreString": "0"},
        ],
        "venue": {"venueName": "Estadio Carlos Alvarado"},
    }
    row.update(changes)
    return row


def concacaf_row(**changes):
    row = {
        "matchId": "concacaf::Football_Match::firpo-away", "status": "UPCOMING",
        "matchDateUtc": "2026-10-22T00:30:00Z", "matchDateLocal": "2026-10-21T18:30:00",
        "home": {"teamId": "firpo", "officialName": "LA Firpo"},
        "away": {"teamId": TEAM, "officialName": "Saprissa"},
        "homeScorePush": 0, "awayScorePush": 0, "stadiumName": "Estadio Magico Gonzalez",
    }
    row.update(changes)
    return row


def legacy_match(**changes):
    data = {
        "id": "existing-calendar-uid", "date": "2026-11-04", "time": "20:00",
        "competition": "Primera Divisi\u00f3n - Torneo de Apertura",
        "home_team": "Herediano", "away_team": "Deportivo Saprissa",
        "venue": "Carlos Alvarado", "status": "scheduled",
        "source_url": "https://www.saprissa.com/partidos/herediano-saprissa",
        "last_seen_at": "2026-10-01T00:00:00+00:00",
    }
    data.update(changes)
    return update.Match.from_dict(data)


class CompetitionSourceTests(unittest.TestCase):
    def test_unafut_uses_utc_and_preserves_local_date(self):
        match, = sources.parse_unafut_matches([unafut_row()], "2373")
        self.assertEqual((match["date"], match["time"]), ("2026-11-05", "20:00"))
        self.assertEqual(match["source_match_id"], "2373:396204")
        self.assertIsNone(match["home_score"])

    def test_unafut_complete_zero_and_live_score_handling(self):
        row = unafut_row(matchStatus="COMPLETE")
        row["competitors"][0]["scoreString"] = "2"
        final, = sources.parse_unafut_matches([row], "2373")
        self.assertEqual((final["status"], final["home_score"], final["away_score"]), ("final", 2, 0))
        row["matchStatus"] = "IN_PROGRESS"
        live, = sources.parse_unafut_matches([row], "2373")
        self.assertEqual(live["status"], "scheduled")
        self.assertIsNone(live["home_score"])

    def test_malformed_sources_are_rejected(self):
        for rows in [[], {}, [unafut_row(matchStatus="UNRECOGNIZED")], [unafut_row(matchTimeUTC="bad-date")]]:
            with self.subTest(rows=rows), self.assertRaises((sources.SourceError, KeyError, ValueError)):
                sources.parse_unafut_matches(rows, "2373")
        row = unafut_row(matchStatus="COMPLETE")
        row["competitors"][0]["scoreString"] = ""
        with self.assertRaises(sources.SourceError):
            sources.parse_unafut_matches([row], "2373")

    def test_unafut_discovers_phases_without_fetching_each_round(self):
        page = '<games-calendar league-slug="costarica" team-id="14044" competition-id="2373"></games-calendar>'
        rounds = [{"phaseName": "Fase Regular"}, {"phaseName": "Fase Regular"}]
        with patch.object(update, "fetch", side_effect=[page, json.dumps(rounds), json.dumps([unafut_row()])]) as fetch:
            self.assertEqual(len(sources.fetch_unafut(fetch)), 1)
            self.assertEqual(fetch.call_count, 3)
            self.assertIn("/rounds/0?", fetch.call_args.args[0])

    def test_concacaf_time_unknown_time_and_scores(self):
        row = concacaf_row()
        match, = sources.parse_concacaf_matches({"matches": [row]}, TEAM)
        self.assertEqual((match["date"], match["time"]), ("2026-10-21", "18:30"))
        row.update(isUnknownKickOffTime=True, status="LIVE", homeScorePush=2, awayScorePush=1)
        match, = sources.parse_concacaf_matches({"matches": [row]}, TEAM)
        self.assertTrue(match["is_time_tbd"])
        self.assertIsNone(match["time"])
        self.assertIsNone(match["home_score"])
        row.update(status="FINISHED", homeScorePush=2, awayScorePush=0)
        match, = sources.parse_concacaf_matches({"matches": [row]}, TEAM)
        self.assertEqual((match["home_score"], match["away_score"]), (2, 0))

    def test_concacaf_reads_current_season_from_page_data(self):
        season = "concacaf::Football_Season::2026"
        config = '35:' + json.dumps({"className": "sdp-club-fixture relative", "seasonIds": [season], "relevantTeamIds": [TEAM]}, separators=(",", ":"))
        page = "<script>self.__next_f.push(" + json.dumps([1, config]) + ")</script>"
        with patch.object(update, "fetch", side_effect=[page, json.dumps({"matches": [concacaf_row()]})]) as fetch:
            self.assertEqual(len(sources.fetch_concacaf(fetch)), 1)
            self.assertIn("Football_Season%3A%3A2026", fetch.call_args.args[0])

    def test_unknown_competition_requires_verified_label(self):
        page = '<games-calendar league-slug="costarica" team-id="14044" competition-id="unknown"></games-calendar>'
        with self.assertRaises(sources.SourceError):
            sources.fetch_unafut(lambda url: page)

    def test_authoritative_schedule_wins_and_uid_survives(self):
        old = legacy_match()
        primary, = [update.Match.from_dict(row) for row in sources.parse_unafut_matches([unafut_row()], "2373")]
        result = update.prioritize_competition_matches([primary], [old], [old.to_dict()])
        match, = result
        self.assertEqual(match.id, old.id)
        self.assertEqual((match.date, match.time), ("2026-11-05", "20:00"))
        self.assertEqual(match.saprissa_url, old.source_url)

    def test_provider_id_handles_large_reschedule_and_removes_stale_supplement(self):
        old = legacy_match(source="unafut", source_match_id="2373:396204", saprissa_url="https://www.saprissa.com/partidos/herediano-saprissa")
        stale = legacy_match(id="stale-supplement")
        primary, = [update.Match.from_dict(row) for row in sources.parse_unafut_matches([unafut_row(matchTimeUTC="2026-12-06 02:00:00")], "2373")]
        result = update.prioritize_competition_matches([primary], [old, stale], [old.to_dict()])
        match, = result
        self.assertEqual(match.id, old.id)
        self.assertEqual(match.date, "2026-12-05")

    def test_same_opponents_in_different_competitions_are_not_merged(self):
        domestic = legacy_match(date="2026-09-16", home_team="Cartagin\u00e9s")
        continental = legacy_match(id="continental-uid", date="2026-09-16", home_team="Cartagin\u00e9s", competition="Primera Divisi\u00f3n - Liga Concacaf")
        primary = legacy_match(id="new-provider", source="concacaf", source_match_id="quarterfinal", date="2026-09-16", home_team="CS Cartagin\u00e9s", competition="Copa Centroamericana de Concacaf")
        result = update.prioritize_competition_matches([primary], [domestic, continental], [domestic.to_dict(), continental.to_dict()])
        self.assertEqual({m.id for m in result}, {"existing-calendar-uid", "continental-uid"})

    def test_official_result_can_correct_a_cached_final_score(self):
        old = legacy_match(status="final", home_score=1, away_score=0)
        row = unafut_row(matchStatus="COMPLETE")
        row["competitors"][0]["scoreString"] = "2"
        primary = update.Match.from_dict(sources.parse_unafut_matches([row], "2373")[0])
        match, = update.prioritize_competition_matches([primary], [old], [old.to_dict()])
        self.assertEqual((match.home_score, match.away_score), (2, 0))

    def test_additional_cup_and_friendly_fixtures_are_retained(self):
        primary = update.Match.from_dict(sources.parse_unafut_matches([unafut_row()], "2373")[0])
        cup = legacy_match(id="cup", date="2026-11-05", competition="Torneo de Copa")
        friendly = legacy_match(id="friendly", date="2026-12-10", competition="Amistoso")
        merged = update.prioritize_competition_matches([primary], [cup, friendly], [])
        self.assertEqual(len(merged), 3)
        self.assertIn("cup", {m.id for m in merged})
        self.assertIn("friendly", {m.id for m in merged})

    def test_ambiguous_legacy_identity_stops_the_merge(self):
        first, second = legacy_match(), legacy_match(id="duplicate-legacy-id")
        primary = update.Match.from_dict(sources.parse_unafut_matches([unafut_row()], "2373")[0])
        with self.assertRaises(sources.SourceError):
            update.prioritize_competition_matches([primary], [first, second], [first.to_dict(), second.to_dict()])

    def test_concacaf_empty_and_wrong_team_data_are_rejected(self):
        with self.assertRaises(sources.SourceError):
            sources.parse_concacaf_matches({"matches": []}, TEAM)
        row = concacaf_row(away={"teamId": "another-team", "officialName": "Other Team"})
        with self.assertRaises(sources.SourceError):
            sources.parse_concacaf_matches({"matches": [row]}, TEAM)

    def test_unchanged_primary_data_keeps_timestamp(self):
        first = update.Match.from_dict(sources.parse_unafut_matches([unafut_row()], "2373")[0])
        first.last_seen_at = "2026-10-01T00:00:00+00:00"
        second = update.Match.from_dict(sources.parse_unafut_matches([unafut_row()], "2373")[0])
        match, = update.prioritize_competition_matches([second], [first], [first.to_dict()])
        self.assertEqual(match.last_seen_at, first.last_seen_at)

    def test_primary_failure_does_not_fall_back_to_bad_saprissa_time(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path, ics_path = Path(directory) / "matches.json", Path(directory) / "saprissa.ics"
            update.write_json(data_path, [legacy_match()])
            ics_path.write_text("previous good feed")
            original_data = data_path.read_text()
            args = argparse.Namespace(data_file=str(data_path), ics_file=str(ics_path), no_aiscore=True)
            with patch.object(update, "load_competition_matches", side_effect=sources.SourceError("upstream failed")), patch.object(update, "fetch") as fetch:
                self.assertEqual(update.run(args), 1)
                fetch.assert_not_called()
            self.assertEqual(data_path.read_text(), original_data)
            self.assertEqual(ics_path.read_text(), "previous good feed")

    def test_supplemental_failure_preserves_existing_extra_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path, ics_path = Path(directory) / "matches.json", Path(directory) / "saprissa.ics"
            extra = legacy_match(id="friendly-uid", competition="Amistoso", home_team="Another Team", date="2026-12-10")
            update.write_json(data_path, [extra])
            primary = update.Match.from_dict(sources.parse_unafut_matches([unafut_row()], "2373")[0])
            args = argparse.Namespace(data_file=str(data_path), ics_file=str(ics_path), no_aiscore=True)
            with patch.object(update, "load_competition_matches", return_value=[primary]), patch.object(update, "fetch", return_value="<html>Changed layout</html>"):
                self.assertEqual(update.run(args), 0)
            self.assertIn("friendly-uid", {m["id"] for m in update.load_existing(data_path)})

    def test_cancelled_match_uses_calendar_cancellation(self):
        match = legacy_match(status="cancelled")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saprissa.ics"
            update.write_ics(path, [match])
            self.assertIn("STATUS:CANCELLED", path.read_text())
            self.assertIn("Estado: cancelado", path.read_text())
