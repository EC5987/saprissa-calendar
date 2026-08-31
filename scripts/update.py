#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen


OFFICIAL_URL = "https://www.saprissa.com/calendario"
RESULTS_URL = "https://www.saprissa.com/resultados"
AISCORE_URL = "https://www.aiscore.com/team-deportivo-saprissa/o17pji0p20i27jw"
TEAM_NAME = "Deportivo Saprissa"
TIMEZONE_ID = "America/Costa_Rica"
SEASON_START = date(2026, 7, 1)
CALENDAR_NAME = "Saprissa - Calendario"

MONTHS = {
    "jan": 1,
    "january": 1,
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "february": 2,
    "febrero": 2,
    "mar": 3,
    "march": 3,
    "marzo": 3,
    "apr": 4,
    "april": 4,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "june": 6,
    "junio": 6,
    "jul": 7,
    "july": 7,
    "julio": 7,
    "aug": 8,
    "august": 8,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "set": 9,
    "septiembre": 9,
    "oct": 10,
    "october": 10,
    "octubre": 10,
    "nov": 11,
    "november": 11,
    "noviembre": 11,
    "dec": 12,
    "december": 12,
    "dic": 12,
    "diciembre": 12,
}

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
    "Lunes",
    "Martes",
    "Miércoles",
    "Miercoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Sabado",
    "Domingo",
)

KNOWN_TEAMS = sorted(
    {
        TEAM_NAME,
        "AD San Carlos",
        "Alajuelense",
        "Alianza FC (PAN)",
        "Cartaginés",
        "Cartagines",
        "CD Olimpia",
        "CS Cartagines",
        "Deportivo Mixco",
        "Escorpiones",
        "Escorpiones Belen",
        "Escorpiones Belén",
        "Herediano",
        "Inter San Carlos",
        "International San Carlos",
        "LD Alajuelense",
        "Liga Deportiva Alajuelense",
        "Mixco",
        "Municipal Liberia",
        "Pérez Zeledón",
        "Perez Zeledon",
        "Puntarenas",
        "Puntarenas FC",
        "Olimpia",
        "San Carlos",
        "Sporting",
        "Sporting FC",
        "UMECIT",
    },
    key=len,
    reverse=True,
)


@dataclass
class Match:
    id: str
    date: str
    time: str | None
    timezone: str
    is_time_tbd: bool
    competition: str
    home_team: str
    away_team: str
    venue: str | None
    status: str = "scheduled"
    home_score: int | None = None
    away_score: int | None = None
    source_url: str = OFFICIAL_URL
    live_score_url: str = AISCORE_URL
    last_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "time": self.time,
            "timezone": self.timezone,
            "is_time_tbd": self.is_time_tbd,
            "competition": self.competition,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "venue": self.venue,
            "status": self.status,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "source_url": self.source_url,
            "live_score_url": self.live_score_url,
            "last_seen_at": self.last_seen_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Match":
        return cls(
            id=str(data["id"]),
            date=str(data["date"]),
            time=data.get("time"),
            timezone=str(data.get("timezone") or TIMEZONE_ID),
            is_time_tbd=bool(data.get("is_time_tbd")),
            competition=str(data.get("competition") or ""),
            home_team=str(data.get("home_team") or ""),
            away_team=str(data.get("away_team") or ""),
            venue=data.get("venue"),
            status=str(data.get("status") or "scheduled"),
            home_score=data.get("home_score"),
            away_score=data.get("away_score"),
            source_url=str(data.get("source_url") or OFFICIAL_URL),
            live_score_url=str(data.get("live_score_url") or AISCORE_URL),
            last_seen_at=str(data.get("last_seen_at") or datetime.now(timezone.utc).isoformat()),
        )


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_link = False
        self._link_href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str | None]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._in_link = True
            self._link_href = dict(attrs).get("href")
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._in_link:
            text = clean_text(" ".join(self._parts))
            if text:
                self.links.append((text, self._link_href))
            self._in_link = False
            self._link_href = None
            self._parts = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text_parts.append(data)
        if self._in_link:
            self._parts.append(data)


def clean_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", value))


def fetch(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; SaprissaCalendar/1.0; "
                "+https://github.com/EC5987/saprissa-calendar)"
            )
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def parse_month(value: str) -> int:
    normalized = normalize_ascii(value).lower().rstrip(".")
    if normalized not in MONTHS:
        raise ValueError(f"Unknown month: {value}")
    return MONTHS[normalized]


def parse_time(value: str) -> tuple[str | None, bool]:
    value = clean_text(value).lower()
    if value in {"tbd", "por definir", "por confirmar", "a definir"}:
        return None, True

    match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*([ap]m)", value)
    if not match:
        return None, True

    hour = int(match.group(1))
    minute = int(match.group(2))
    period = match.group(3)
    if period == "pm" and hour != 12:
        hour += 12
    if period == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}", False


def make_match_id(match_date: date, competition: str, home: str, away: str) -> str:
    raw = "|".join([match_date.isoformat(), normalize_team(competition), normalize_team(home), normalize_team(away)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_ascii(value: str) -> str:
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "ñ": "n",
        "Ñ": "N",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def normalize_team(value: str) -> str:
    value = normalize_ascii(value).lower()
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\b(fc|cd|cs|ad|ld)\b", " ", value)
    value = re.sub(r"\b(deportivo|liga deportiva|club sport)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def teams_match(a: str, b: str) -> bool:
    left = normalize_team(a)
    right = normalize_team(b)
    return bool(left and right and (left == right or left in right or right in left))


def split_known_team_at_end(value: str) -> tuple[str, str] | None:
    normalized = clean_text(value)
    for team in KNOWN_TEAMS:
        if normalized.endswith(team):
            return clean_text(normalized[: -len(team)]), team
    return None


def split_known_team_at_start(value: str) -> tuple[str, str] | None:
    normalized = clean_text(value)
    for team in KNOWN_TEAMS:
        if normalized.startswith(team):
            return team, clean_text(normalized[len(team) :])
    return None


def parse_official_match(text: str, href: str | None) -> Match | None:
    text = clean_text(text)
    if "(FF)" in text:
        return None

    weekday_pattern = "|".join(re.escape(day) for day in WEEKDAYS)
    match = re.match(
        rf"^(?:{weekday_pattern})\s+"
        r"(?P<day>\d{1,2})\s+de\s+"
        r"(?P<month>[A-Za-zÁÉÍÓÚáéíóúñÑ.]+)\s*,\s*"
        r"(?P<year>\d{4})\s*-\s*"
        r"(?P<time>(?:\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))|(?:TBD|Por definir|Por confirmar|A definir))\s+"
        r"(?P<body>.+)$",
        text,
    )
    if not match:
        return None

    body = clean_text(re.sub(r"\bLive$", "", match.group("body")).strip())
    body = re.sub(r"\s*--\s*--\s*", "----", body)
    if "----" not in body:
        return None

    left, right = [clean_text(part) for part in body.split("----", 1)]
    left_parts = split_known_team_at_end(left)
    right_parts = split_known_team_at_start(right)
    if not left_parts or not right_parts:
        return None

    competition, home = left_parts
    away, venue = right_parts
    if not teams_match(home, TEAM_NAME) and not teams_match(away, TEAM_NAME):
        return None

    match_date = date(int(match.group("year")), parse_month(match.group("month")), int(match.group("day")))
    match_time, is_time_tbd = parse_time(match.group("time"))

    source_url = OFFICIAL_URL
    if href:
        source_url = href if href.startswith("http") else f"https://www.saprissa.com{href}"

    return Match(
        id=make_match_id(match_date, competition, home, away),
        date=match_date.isoformat(),
        time=match_time,
        timezone=TIMEZONE_ID,
        is_time_tbd=is_time_tbd,
        competition=competition,
        home_team=home,
        away_team=away,
        venue=venue or None,
        source_url=source_url,
    )


def parse_official_result(text: str, href: str | None) -> Match | None:
    text = clean_text(text)
    if "(FF)" in text:
        return None

    weekday_pattern = "|".join(re.escape(day) for day in WEEKDAYS)
    match = re.match(
        rf"^(?:{weekday_pattern})\s+"
        r"(?P<day>\d{1,2})\s+de\s+"
        r"(?P<month>[A-Za-zÁÉÍÓÚáéíóúñÑ.]+)\s*,\s*"
        r"(?P<year>\d{4})\s*-\s*"
        r"(?P<time>(?:\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))|(?:TBD|Por definir|Por confirmar|A definir))\s+"
        r"(?P<body>.+)$",
        text,
    )
    if not match:
        return None

    body = clean_text(re.sub(r"\bLive$", "", match.group("body")).strip())
    body_match = re.match(r"(?P<left>.+?)\s+(?P<home_score>\d+)\s*--\s*(?P<away_score>\d+)\s*--\s*(?P<right>.+)$", body)
    if not body_match:
        return None

    left = clean_text(body_match.group("left"))
    right = clean_text(body_match.group("right"))
    left_parts = split_known_team_at_end(left)
    right_parts = split_known_team_at_start(right)
    if not left_parts or not right_parts:
        return None

    competition, home = left_parts
    away, venue = right_parts
    if not teams_match(home, TEAM_NAME) and not teams_match(away, TEAM_NAME):
        return None

    match_date = date(int(match.group("year")), parse_month(match.group("month")), int(match.group("day")))
    if match_date < SEASON_START:
        return None

    match_time, is_time_tbd = parse_time(match.group("time"))

    source_url = RESULTS_URL
    if href:
        source_url = href if href.startswith("http") else f"https://www.saprissa.com{href}"

    return Match(
        id=make_match_id(match_date, competition, home, away),
        date=match_date.isoformat(),
        time=match_time,
        timezone=TIMEZONE_ID,
        is_time_tbd=is_time_tbd,
        competition=competition,
        home_team=home,
        away_team=away,
        venue=venue or None,
        status="final",
        home_score=int(body_match.group("home_score")),
        away_score=int(body_match.group("away_score")),
        source_url=source_url,
    )


def parse_official_schedule(page_html: str) -> list[Match]:
    parser = LinkTextParser()
    parser.feed(page_html)

    matches: list[Match] = []
    seen: set[str] = set()
    for text, href in parser.links:
        if not any(text.startswith(day) for day in WEEKDAYS):
            continue
        parsed = parse_official_match(text, href)
        if parsed and parsed.id not in seen:
            matches.append(parsed)
            seen.add(parsed.id)

    return sorted(matches, key=lambda item: (item.date, item.time or "99:99", item.home_team, item.away_team))


def parse_official_results(page_html: str) -> list[Match]:
    parser = LinkTextParser()
    parser.feed(page_html)

    matches: list[Match] = []
    seen: set[str] = set()
    for text, href in parser.links:
        if not any(text.startswith(day) for day in WEEKDAYS):
            continue
        parsed = parse_official_result(text, href)
        if parsed and parsed.id not in seen:
            matches.append(parsed)
            seen.add(parsed.id)

    return sorted(matches, key=lambda item: (item.date, item.time or "99:99", item.home_team, item.away_team))


def parse_aiscore_scores(page_html: str) -> list[dict]:
    structured_scores = parse_aiscore_structured_scores(page_html)
    if structured_scores:
        return structured_scores

    parser = LinkTextParser()
    parser.feed(page_html)
    text = clean_text(" ".join(parser.text_parts))

    competition_pattern = r"(Costa Rica Primera Division|CONCACAF Central American Cup|Costa Cup|Supercopa de Costa Rica)"
    event_pattern = re.compile(
        r"(?P<day>\d{2})\s+(?P<month>[A-Za-z]{3})\s+(?P<clock>\d{2}:\d{2})\s+"
        + competition_pattern
        + r"\s+(?P<home>.+?)\s+(?P<score>\d+\s*-\s*\d+)\s+(?P<away>.+?)"
        + r"(?=\s+\d{2}\s+[A-Za-z]{3}\s+\d{2}:\d{2}\s+"
        + competition_pattern
        + r"|\s+Deportivo Saprissa Stats|\s+Apps|\Z)"
    )

    scores = []
    for match in event_pattern.finditer(text):
        home_score, away_score = [int(part.strip()) for part in match.group("score").split("-")]
        scores.append(
            {
                "day": int(match.group("day")),
                "month": parse_month(match.group("month")),
                "start_at": None,
                "match_url": AISCORE_URL,
                "competition": clean_text(match.group(4)),
                "home_team": clean_text(match.group("home")),
                "away_team": clean_text(match.group("away")),
                "home_score": home_score,
                "away_score": away_score,
            }
        )
    return scores


def parse_aiscore_structured_scores(page_html: str) -> list[dict]:
    row_start_pattern = r'<div itemscope="itemscope" itemtype="http://schema.org/SportsEvent"'
    starts = [match.start() for match in re.finditer(row_start_pattern, page_html)]
    scores: list[dict] = []

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(page_html)
        row_html = page_html[start:end]
        metadata = {
            match.group("prop"): html.unescape(match.group("content"))
            for match in re.finditer(
                r'<meta[^>]+itemprop="(?P<prop>name|url|startDate|location|Organization)"[^>]+content="(?P<content>[^"]*)"',
                row_html,
            )
        }

        home_match = re.search(r'<span[^>]+itemprop="homeTeam"[^>]*>(?P<team>.*?)</span>', row_html, re.DOTALL)
        away_match = re.search(r'<span[^>]+itemprop="awayTeam"[^>]*>(?P<team>.*?)</span>', row_html, re.DOTALL)
        score_match = re.search(
            r'<a[^>]+itemprop="url"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<score>.*?)</a>',
            row_html,
            re.DOTALL,
        )

        if not home_match or not away_match or not score_match:
            continue

        score_text = strip_tags(score_match.group("score"))
        score_parts = re.fullmatch(r"(?P<home>\d+)\s*-\s*(?P<away>\d+)", score_text)
        if not score_parts:
            continue

        start_at = metadata.get("startDate")
        try:
            start_date = datetime.fromisoformat(start_at).date() if start_at else None
        except ValueError:
            start_date = None

        match_url = metadata.get("url") or score_match.group("href") or AISCORE_URL
        if match_url.startswith("/"):
            match_url = f"https://www.aiscore.com{match_url}"

        scores.append(
            {
                "day": start_date.day if start_date else None,
                "month": start_date.month if start_date else None,
                "start_at": start_at,
                "match_url": match_url,
                "competition": clean_text(metadata.get("Organization") or ""),
                "home_team": strip_tags(home_match.group("team")),
                "away_team": strip_tags(away_match.group("team")),
                "home_score": int(score_parts.group("home")),
                "away_score": int(score_parts.group("away")),
            }
        )

    return scores


def match_start_datetime(match: Match) -> datetime | None:
    if not match.time:
        return None

    match_date = date.fromisoformat(match.date)
    match_time = time.fromisoformat(match.time)
    return datetime.combine(match_date, match_time, tzinfo=timezone(timedelta(hours=-6)))


def score_is_near_match(match: Match, score: dict) -> bool:
    if score.get("start_at"):
        try:
            score_start = datetime.fromisoformat(str(score["start_at"])).astimezone(timezone(timedelta(hours=-6)))
        except ValueError:
            score_start = None
        match_start = match_start_datetime(match)
        if score_start and match_start:
            return abs((score_start - match_start).total_seconds()) <= 12 * 60 * 60

    match_date = date.fromisoformat(match.date)
    return score.get("month") == match_date.month and score.get("day") == match_date.day


def enrich_scores(matches: list[Match], scores: list[dict]) -> None:
    for match in matches:
        for score in scores:
            if not score_is_near_match(match, score):
                continue
            if teams_match(match.home_team, score["home_team"]) and teams_match(match.away_team, score["away_team"]):
                match.status = "final" if likely_finished(match) else "in_progress"
                match.home_score = score["home_score"]
                match.away_score = score["away_score"]
                if score.get("match_url"):
                    match.live_score_url = str(score["match_url"])
                break


def preserve_existing_metadata(matches: list[Match], existing: list[dict]) -> None:
    existing_by_id = {item.get("id"): item for item in existing}
    for match in matches:
        old = existing_by_id.get(match.id)
        if not old:
            continue
        if old.get("last_seen_at"):
            match.last_seen_at = old["last_seen_at"]
        if old.get("status") == "final":
            match.status = "final"
            match.home_score = old.get("home_score")
            match.away_score = old.get("away_score")


def costa_rica_today() -> date:
    return datetime.now(timezone(timedelta(hours=-6))).date()


def merge_matches(
    result_matches: list[Match],
    fixture_matches: list[Match],
    existing: list[dict],
    *,
    prune_stale_future: bool,
) -> list[Match]:
    merged_by_id = {match.id: match for match in result_matches}
    for match in fixture_matches:
        merged_by_id[match.id] = match

    official_ids = set(merged_by_id)
    merged = list(merged_by_id.values())
    today = costa_rica_today()

    for item in existing:
        try:
            old_match = Match.from_dict(item)
            old_date = date.fromisoformat(old_match.date)
        except (KeyError, TypeError, ValueError):
            continue
        if old_match.id in official_ids:
            continue
        if not prune_stale_future or old_date <= today:
            merged.append(old_match)

    return sorted(merged, key=lambda item: (item.date, item.time or "99:99", item.home_team, item.away_team))


def match_has_started(match: Match) -> bool:
    match_date = date.fromisoformat(match.date)
    now = datetime.now(timezone(timedelta(hours=-6)))

    if not match.time:
        return match_date < now.date()

    match_time = time.fromisoformat(match.time)
    start = datetime.combine(match_date, match_time, tzinfo=timezone(timedelta(hours=-6)))
    return start <= now


def likely_finished(match: Match) -> bool:
    match_date = date.fromisoformat(match.date)
    now = datetime.now(timezone(timedelta(hours=-6)))

    if not match.time:
        return match_date < now.date()

    match_time = time.fromisoformat(match.time)
    start = datetime.combine(match_date, match_time, tzinfo=timezone(timedelta(hours=-6)))
    return now >= start + timedelta(hours=6)


def needs_aiscore_enrichment(matches: list[Match]) -> bool:
    for match in matches:
        if not match_has_started(match):
            continue
        if match.status != "final" or match.home_score is None or match.away_score is None:
            return True
    return False


def is_match_window_now(match: Match) -> bool:
    match_date = date.fromisoformat(match.date)
    now = datetime.now(timezone(timedelta(hours=-6)))

    if not match.time:
        return match_date == now.date()

    match_time = time.fromisoformat(match.time)
    start = datetime.combine(match_date, match_time, tzinfo=timezone(timedelta(hours=-6)))
    return start - timedelta(minutes=30) <= now <= start + timedelta(hours=6)


def should_run_match_window_update(existing: list[dict]) -> bool:
    if not existing:
        return True

    for item in existing:
        try:
            match = Match.from_dict(item)
        except (KeyError, TypeError, ValueError):
            continue
        if is_match_window_now(match):
            return True
    return False


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def write_json(path: Path, matches: list[Match]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [match.to_dict() for match in matches]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def fold_ics_line(line: str) -> list[str]:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]

    lines = []
    current = ""
    for char in line:
        candidate = current + char
        if len(candidate.encode("utf-8")) > 75:
            lines.append(current)
            current = " " + char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def add_ics_line(lines: list[str], line: str) -> None:
    lines.extend(fold_ics_line(line))


def format_ics_stamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def format_ics_datetime(match: Match) -> str:
    parsed_date = date.fromisoformat(match.date)
    if not match.time:
        return parsed_date.strftime("%Y%m%d")
    parsed_time = time.fromisoformat(match.time)
    return datetime.combine(parsed_date, parsed_time).strftime("%Y%m%dT%H%M%S")


def spanish_status(value: str) -> str:
    statuses = {
        "scheduled": "programado",
        "in_progress": "en vivo",
        "final": "finalizado",
    }
    return statuses.get(value, value)


def format_location(venue: str) -> str:
    if venue.lower().startswith("estadio "):
        return venue
    return f"Estadio {venue}"


def write_ics(path: Path, matches: Iterable[Match]) -> None:
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EC5987//Saprissa Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
        f"X-WR-TIMEZONE:{TIMEZONE_ID}",
        "BEGIN:VTIMEZONE",
        f"TZID:{TIMEZONE_ID}",
        f"X-LIC-LOCATION:{TIMEZONE_ID}",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:-0600",
        "TZOFFSETTO:-0600",
        "TZNAME:CST",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for match in matches:
        summary = f"{match.home_team} - {match.away_team}"
        if match.status in {"final", "in_progress"} and match.home_score is not None and match.away_score is not None:
            summary += f" ({match.home_score}-{match.away_score})"

        description_lines = [
            match.competition,
            f"Estado: {spanish_status(match.status)}",
            "Minuto a minuto:",
            match.source_url,
            match.live_score_url,
        ]

        lines.append("BEGIN:VEVENT")
        add_ics_line(lines, f"UID:{match.id}@saprissa-calendar.ec5987")
        add_ics_line(lines, f"DTSTAMP:{format_ics_stamp(match.last_seen_at)}")
        add_ics_line(lines, f"SUMMARY:{ics_escape(summary)}")

        if match.is_time_tbd or not match.time:
            start = date.fromisoformat(match.date)
            end = start + timedelta(days=1)
            add_ics_line(lines, f"DTSTART;VALUE=DATE:{start:%Y%m%d}")
            add_ics_line(lines, f"DTEND;VALUE=DATE:{end:%Y%m%d}")
        else:
            start_dt = format_ics_datetime(match)
            parsed_start = datetime.strptime(start_dt, "%Y%m%dT%H%M%S")
            end_dt = (parsed_start + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
            add_ics_line(lines, f"DTSTART;TZID={TIMEZONE_ID}:{start_dt}")
            add_ics_line(lines, f"DTEND;TZID={TIMEZONE_ID}:{end_dt}")

        if match.venue:
            add_ics_line(lines, f"LOCATION:{ics_escape(format_location(match.venue))}")
        add_ics_line(lines, f"DESCRIPTION:{ics_escape(chr(10).join(description_lines))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    data_file = Path(args.data_file)
    ics_file = Path(args.ics_file)
    existing = load_existing(data_file)

    if args.match_window_only and not should_run_match_window_update(existing):
        print("No known match is currently near its live window. Skipping update.")
        return 0

    fixture_matches: list[Match] = []
    result_matches: list[Match] = []
    fixture_source_ok = False

    try:
        official_html = fetch(OFFICIAL_URL)
        fixture_matches = parse_official_schedule(official_html)
        fixture_source_ok = True
    except (URLError, TimeoutError) as error:
        print(f"Saprissa calendar fetch skipped: {error}", file=sys.stderr)

    try:
        results_html = fetch(RESULTS_URL)
        result_matches = parse_official_results(results_html)
    except (URLError, TimeoutError) as error:
        print(f"Saprissa results fetch skipped: {error}", file=sys.stderr)

    if not fixture_matches and not result_matches and not existing:
        print("No matches found on the official Saprissa calendar page.", file=sys.stderr)
        return 1

    preserve_existing_metadata(fixture_matches, existing)
    preserve_existing_metadata(result_matches, existing)
    matches = merge_matches(
        result_matches,
        fixture_matches,
        existing,
        prune_stale_future=fixture_source_ok,
    )

    if not args.no_aiscore and needs_aiscore_enrichment(matches):
        try:
            scores = parse_aiscore_scores(fetch(AISCORE_URL))
            enrich_scores(matches, scores)
        except (URLError, TimeoutError, ValueError) as error:
            print(f"AiScore enrichment skipped: {error}", file=sys.stderr)

    write_json(data_file, matches)
    write_ics(ics_file, matches)
    print(f"Wrote {len(matches)} matches to {data_file} and {ics_file}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update the Saprissa iCal feed.")
    parser.add_argument("--data-file", default="data/matches.json")
    parser.add_argument("--ics-file", default="public/saprissa.ics")
    parser.add_argument("--no-aiscore", action="store_true", help="Skip best-effort AiScore score enrichment.")
    parser.add_argument(
        "--match-window-only",
        action="store_true",
        help="Skip quickly unless stored match data shows a match is near kickoff or currently live.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
