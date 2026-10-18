#!/usr/bin/env python3
"""Check API-Football access without modifying the published calendar."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


API_BASE = "https://v3.football.api-sports.io"


class ApiFootballError(RuntimeError):
    pass


class ApiFootballClient:
    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise ApiFootballError("API_FOOTBALL_KEY is not configured.")
        self.api_key = api_key.strip()

    def get(self, endpoint: str, **params: str | int) -> list[dict]:
        if endpoint not in {"teams", "fixtures"}:
            raise ApiFootballError("Unsupported API-Football endpoint.")
        request = Request(
            f"{API_BASE}/{endpoint}?{urlencode(params)}",
            headers={"x-apisports-key": self.api_key, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
        except HTTPError as error:
            raise ApiFootballError(f"API-Football returned HTTP {error.code} for /{endpoint}.") from None
        except (URLError, TimeoutError):
            raise ApiFootballError(f"API-Football request failed for /{endpoint}.") from None
        except (ValueError, UnicodeError):
            raise ApiFootballError(f"API-Football returned invalid JSON for /{endpoint}.") from None

        if not isinstance(data, dict):
            raise ApiFootballError(f"API-Football returned an invalid response for /{endpoint}.")
        if data.get("errors"):
            message = json.dumps(data["errors"], ensure_ascii=True).replace(self.api_key, "[REDACTED]")
            raise ApiFootballError(f"API-Football /{endpoint}: {message[:2000]}")
        if not isinstance(data.get("response"), list):
            raise ApiFootballError(f"API-Football returned no response list for /{endpoint}.")
        if data.get("paging", {}).get("total", 1) != 1:
            raise ApiFootballError(f"API-Football /{endpoint} returned multiple pages; refusing an incomplete list.")
        return data["response"]


def check_access(api_key: str, season: int) -> None:
    client = ApiFootballClient(api_key)
    teams = client.get("teams", search="saprissa")
    candidates = [
        item["team"] for item in teams
        if item.get("team", {}).get("country") in {"Costa-Rica", "Costa Rica"}
        and item["team"].get("name", "").casefold() in {"saprissa", "deportivo saprissa"}
    ]
    if len(candidates) != 1:
        raise ApiFootballError(f"Expected one Costa Rican Saprissa team; found {len(candidates)}.")
    team = candidates[0]
    team_id = int(team["id"])
    print(f"Team verified: {team['name']} (ID {team_id}).", flush=True)
    fixtures = client.get("fixtures", team=team_id, season=season)
    if not fixtures:
        raise ApiFootballError(f"No Saprissa fixtures returned for season {season}; migration is not ready.")

    competitions = sorted({item["league"]["name"] for item in fixtures})
    print(f"Season {season}: {len(fixtures)} fixtures.")
    print("Competitions: " + ", ".join(competitions))
    print("Kickoff times below use America/Costa_Rica. Scores are shown only for finished games.")
    for item in sorted(fixtures, key=lambda row: row["fixture"]["date"]):
        fixture = item["fixture"]
        kickoff = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00"))
        local = kickoff.astimezone(ZoneInfo("America/Costa_Rica"))
        if local.date().isoformat() < f"{season}-07-01":
            continue
        home, away = item["teams"]["home"], item["teams"]["away"]
        if team_id not in {home["id"], away["id"]}:
            raise ApiFootballError("A fixture does not belong to the verified Saprissa team.")
        status = fixture["status"]["short"]
        score = ""
        if status in {"FT", "AET", "PEN"}:
            score = f" {item['goals']['home']}-{item['goals']['away']}"
        print(
            f"{local:%Y-%m-%d %H:%M} | {home['name']} - {away['name']} | "
            f"{item['league']['name']} | {status}{score} | fixture {fixture['id']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    try:
        check_access(os.environ.get("API_FOOTBALL_KEY", ""), args.season)
    except (ApiFootballError, KeyError, TypeError, ValueError) as error:
        # Provider errors may contain echoed request data. Always redact the key.
        key = os.environ.get("API_FOOTBALL_KEY", "").strip()
        message = str(error).replace(key, "[REDACTED]") if key else str(error)
        print(f"Coverage check failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
