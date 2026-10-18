"""Read the structured feeds used by the official competition websites."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo


UNAFUT_URL = "https://www.unafut.com/en/club/14044/deportivo-saprissa"
UNAFUT_API = "https://gapi.pixeles.club/ligas/costarica/api"
UNAFUT_TEAM = 14044
CONCACAF_URL = "https://www.concacaf.com/competitions/central-american-cup/clubs/saprissa/index"
CONCACAF_API = "https://api-sdp.concacaf.com/v1/concacaf/football"
COSTA_RICA = ZoneInfo("America/Costa_Rica")
SEASON_START = date(2026, 7, 1)
UNAFUT_COMPETITIONS = {"2373": "Primera Divisi\u00f3n - Torneo de Apertura"}


class SourceError(ValueError):
    pass


class SourcePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.competitions: set[str] = set()
        self.flight_parts: list[str] = []
        self._script = False
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        attrs = dict(attrs)
        if tag == "games-calendar" and attrs.get("team-id") == str(UNAFUT_TEAM):
            if attrs.get("league-slug") == "costarica" and attrs.get("competition-id"):
                self.competitions.add(attrs["competition-id"])
        if tag == "script":
            self._script = True
            self._parts = []

    def handle_data(self, value: str) -> None:
        if self._script:
            self._parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._script:
            return
        self._script = False
        for match in re.finditer(r"self\.__next_f\.push\((\[.*\])\)\s*;?", "".join(self._parts)):
            payload = json.loads(match.group(1))
            if len(payload) > 1 and payload[0] == 1 and isinstance(payload[1], str):
                self.flight_parts.append(payload[1])


def utc_kickoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(COSTA_RICA)


def final_score(value) -> int:
    if isinstance(value, bool) or not str(value).isdigit():
        raise SourceError("A completed match is missing a valid final score.")
    return int(value)


def fixture(source, source_id, kickoff, home, away, competition, venue, status, source_url,
            home_score=None, away_score=None, unknown_time=False) -> dict:
    if not home.strip() or not away.strip():
        raise SourceError("A match is missing a team name.")
    return {
        "id": hashlib.sha1(f"{source}|{source_id}".encode()).hexdigest()[:16],
        "source": source,
        "source_match_id": str(source_id),
        "date": kickoff.date().isoformat(),
        "time": None if unknown_time else kickoff.strftime("%H:%M"),
        "timezone": "America/Costa_Rica",
        "is_time_tbd": unknown_time,
        "home_team": home.strip(),
        "away_team": away.strip(),
        "competition": competition,
        "venue": venue or None,
        "status": status,
        "home_score": final_score(home_score) if status == "final" else None,
        "away_score": final_score(away_score) if status == "final" else None,
        "source_url": source_url,
    }


def parse_unafut_matches(rows, competition_id: str) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise SourceError("UNAFUT returned an empty or invalid match list.")
    statuses = {
        "SCHEDULED": "scheduled", "IN_PROGRESS": "scheduled", "COMPLETE": "final",
        "POSTPONED": "postponed", "CANCELLED": "cancelled", "ABANDONED": "abandoned",
        "DELAYED": "delayed", "SUSPENDED": "suspended",
    }
    matches = []
    for row in rows:
        teams = row["competitors"]
        if len(teams) != 2 or UNAFUT_TEAM not in {int(t["competitorId"]) for t in teams}:
            raise SourceError("UNAFUT returned a match for a different team.")
        kickoff = utc_kickoff(row["matchTimeUTC"])
        if kickoff.date() < SEASON_START:
            continue
        status = statuses[row["matchStatus"]]
        home, away = teams
        home_name = "Deportivo Saprissa" if int(home["competitorId"]) == UNAFUT_TEAM else home["competitorName"]
        away_name = "Deportivo Saprissa" if int(away["competitorId"]) == UNAFUT_TEAM else away["competitorName"]
        venue = (row.get("venue") or {}).get("venueName")
        if venue and venue.isupper():
            venue = venue.title()
        matches.append(fixture(
            "unafut", f"{competition_id}:{row['matchId']}", kickoff,
            home_name, away_name, UNAFUT_COMPETITIONS.get(competition_id, "Primera Divisi\u00f3n"),
            venue, status, f"https://www.unafut.com/en/partido/{row['matchId']}",
            home.get("scoreString"), away.get("scoreString"),
        ))
    return matches


def fetch_unafut(fetch) -> list[dict]:
    page = SourcePageParser()
    page.feed(fetch(UNAFUT_URL))
    if not page.competitions:
        raise SourceError("No senior competition configuration found on UNAFUT's Saprissa page.")
    matches: dict[str, dict] = {}
    for competition in sorted(page.competitions):
        if competition not in UNAFUT_COMPETITIONS:
            raise SourceError(f"New UNAFUT competition {competition} needs a verified competition label before publishing.")
        query = urlencode({"competitionId": competition, "teamId": UNAFUT_TEAM})
        rounds = json.loads(fetch(f"{UNAFUT_API}/rounds?{query}"))
        if not isinstance(rounds, list) or not rounds:
            raise SourceError("UNAFUT returned no competition rounds.")
        for phase in sorted({row["phaseName"] for row in rounds}):
            query = urlencode({"competitionId": competition, "teamId": UNAFUT_TEAM, "phaseName": phase})
            rows = json.loads(fetch(f"{UNAFUT_API}/rounds/0?{query}"))
            for match in parse_unafut_matches(rows, competition):
                matches[match["source_match_id"]] = match
    if not matches:
        raise SourceError("UNAFUT returned no matches from the supported season.")
    print(f"UNAFUT: {len(matches)} matches across {len(page.competitions)} competition(s).")
    return list(matches.values())


def parse_concacaf_matches(data, team_id: str) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("matches"), list) or not data["matches"]:
        raise SourceError("Concacaf returned an empty or invalid match list.")
    statuses = {
        "UPCOMING": "scheduled", "LIVE": "scheduled", "IN_PROGRESS": "scheduled", "FINISHED": "final",
        "POSTPONED": "postponed", "CANCELLED": "cancelled", "ABANDONED": "abandoned",
        "DELAYED": "delayed", "SUSPENDED": "suspended",
    }
    matches = []
    for row in data["matches"]:
        home, away = row["home"], row["away"]
        if team_id not in {home["teamId"], away["teamId"]}:
            raise SourceError("Concacaf returned a match for a different team.")
        kickoff = utc_kickoff(row["matchDateUtc"])
        unknown_time = row.get("isUnknownKickOffTime", False)
        if unknown_time and row.get("matchDateLocal"):
            kickoff = datetime.fromisoformat(row["matchDateLocal"]).replace(tzinfo=COSTA_RICA)
        if kickoff.date() < SEASON_START:
            continue
        home_name = "Deportivo Saprissa" if home["teamId"] == team_id else home["officialName"]
        away_name = "Deportivo Saprissa" if away["teamId"] == team_id else away["officialName"]
        match_id = row["matchId"]
        matches.append(fixture(
            "concacaf", match_id, kickoff, home_name, away_name,
            "Copa Centroamericana de Concacaf", row.get("stadiumName"), statuses[row["status"]],
            CONCACAF_URL,
            row.get("homeScorePush"), row.get("awayScorePush"), unknown_time,
        ))
    if not matches:
        raise SourceError("Concacaf returned no matches from the supported season.")
    return matches


def fetch_concacaf(fetch) -> list[dict]:
    page = SourcePageParser()
    page.feed(fetch(CONCACAF_URL))
    config = next((part for part in page.flight_parts if '"className":"sdp-club-fixture ' in part), None)
    if config is None:
        raise SourceError("No club fixture configuration found on Concacaf's Saprissa page.")
    # These are JSON arrays in Next.js page data, not JavaScript to execute.
    seasons = re.search(r'"seasonIds":(\[[^\]]+\])', config)
    teams = re.search(r'"relevantTeamIds":(\[[^\]]+\])', config)
    if not seasons or not teams:
        raise SourceError("Concacaf's fixture configuration is missing season or team IDs.")
    season_ids, team_ids = json.loads(seasons[1]), json.loads(teams[1])
    if not season_ids or len(team_ids) != 1 or not team_ids[0].startswith("concacaf::Football_Team::"):
        raise SourceError("Concacaf's fixture configuration contains invalid IDs.")
    matches = {}
    for season in season_ids:
        url = f"{CONCACAF_API}/seasons/{quote(season, safe='')}/matches?{urlencode({'relevantTeamIds': team_ids[0]})}"
        for match in parse_concacaf_matches(json.loads(fetch(url)), team_ids[0]):
            matches[match["source_match_id"]] = match
    print(f"Concacaf: {len(matches)} matches.")
    return list(matches.values())
