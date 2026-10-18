# Saprissa - Calendario

A small, dependency-free Python project that publishes a subscribable iCal feed for Deportivo Saprissa matches.

Schedules and final results use the competition organizers first:

| Source | Role |
| --- | --- |
| [UNAFUT](https://www.unafut.com/en/club/14044/deportivo-saprissa) | Primary for the domestic competitions exposed on its senior Saprissa page; currently Apertura 2026. |
| [Concacaf](https://www.concacaf.com/competitions/central-american-cup/clubs/saprissa/index) | Primary for Saprissa's Central American Cup fixtures and results. |
| [Saprissa calendar](https://www.saprissa.com/calendario) and [results](https://www.saprissa.com/resultados) | Supplemental fixtures not covered by the organizers, including friendlies and domestic cup matches absent from UNAFUT's feed. Cannot override organizer data. |
| [AiScore](https://www.aiscore.com/team-deportivo-saprissa/o17pji0p20i27jw) | Best-effort fallback only when a completed match is missing a final score. |

No paid API or API key is needed for this pipeline. The adapters use the same public JSON feeds as the UNAFUT and Concacaf websites. These are website endpoints, not guaranteed developer APIs; if either primary source fails validation or cannot be reached, the update fails before changing the published feed.

Domestic cup coverage has **not** been verified in UNAFUT's current feed. Cup fixtures remain eligible for the Saprissa supplement until an official cup competition feed is identified. The adapter discovers competition IDs from UNAFUT's page and requires a verified label in `UNAFUT_COMPETITIONS` in `scripts/official_sources.py` before using a new competition. It loads all phases, including playoff rounds when published. Concacaf's team and season IDs are discovered from its club page.

## Files

```text
data/matches.json        Stored match data
public/saprissa.ics      Public calendar feed
public/index.html        Small GitHub Pages entry page
scripts/update.py        Scraper, optional score enrichment, and ICS generator
scripts/official_sources.py  UNAFUT and Concacaf website-feed adapters
tests/                  Source, reconciliation, and calendar regression tests
.github/workflows/update.yml
```

## Local Testing

From the repo root:

```bash
python3 scripts/update.py
```

That command updates:

```text
data/matches.json
public/saprissa.ics
```

To disable the AiScore fallback while testing:

```bash
python3 scripts/update.py --no-aiscore
```

To run the offline regression tests:

```bash
python3 -m unittest discover -s tests
```

To write outputs somewhere else:

```bash
python3 scripts/update.py --data-file /tmp/matches.json --ics-file /tmp/saprissa.ics
```

## Calendar Behavior

### API-Football Evaluation

The separate, unscheduled `Check API-Football coverage` workflow was used to evaluate a commercial alternative; it is not part of the calendar's hourly updates. It uses the repository Actions secret `API_FOOTBALL_KEY`; never commit the key or put it in a URL. It calls `/teams?search=saprissa` and `/fixtures?team=TEAM_ID&season=2026` (two requests per test), then logs competition coverage and kickoff times in Costa Rica time. API plan errors are reported even when the HTTP response is successful.

The October 18, 2026 check successfully authenticated and identified Deportivo Saprissa as team ID `816`. The fixture request was rejected with: `Free plans do not have access to this season, try from 2022 to 2024.` The current free plan therefore cannot replace the published calendar's data source. Re-run this workflow after a plan change before enabling a migration; current-season fixture coverage and kickoff accuracy still need verification.

### Published Feed

- Match times are stored as Costa Rica time: `America/Costa_Rica`.
- Calendar apps should convert the event time to each subscriber's local time zone.
- Matches with unknown times are emitted as all-day placeholder events.
- Event titles use the format `Home Team - Away Team`.
- Completed matches include the score when available, like `Home Team - Away Team (2-1)`.
- Organizer kickoff times, stadiums, statuses, and final results take precedence over Saprissa's entries and cached scores.
- UTC timestamps are converted with `America/Costa_Rica`, rather than copying the browser's displayed local time.
- A targeted correction for October 18's Saprissa supplement remains as a fallback; UNAFUT independently supplies the correct 11:00 a.m. kickoff.
- Team names and stadiums are read from structured fields, without a fixed opponent list.
- If either organizer feed is unavailable or malformed, the current feed remains untouched. A failed Saprissa supplement is logged while organizer updates can continue.
- Provider match IDs preserve event identity through reschedules. Migration matches older events by competition, home/away teams, and nearby dates; the original Saprissa link is retained for deduplication even after later reschedules.
- Ambiguous event matches stop publication instead of guessing or duplicating events.
- Completed men's matches from July 1, 2026 onward are included. Historical and supplemental fixtures are retained when absent from a current source.
- AiScore is only used as a fallback when a final score is missing from the other sources.
- Cancelled fixtures retain their event ID and receive `STATUS:CANCELLED`; postponed, delayed, suspended, and abandoned states use Spanish notes.
- Live, in-progress score changes are intentionally not published to the calendar.
- Past matches already stored in `data/matches.json` are preserved so scores can still be added after they leave the official schedule page.

## Apple Calendar Subscription

The public feed URL is:

```text
https://ec5987.github.io/saprissa-calendar/saprissa.ics
```

On macOS:

1. Open Calendar.
2. Choose `File` > `New Calendar Subscription`.
3. Paste the `.ics` URL.
4. Set auto-refresh to a cadence you like.

On iPhone:

1. Open Settings.
2. Go to `Calendar` > `Accounts` > `Add Account` > `Other`.
3. Choose `Add Subscribed Calendar`.
4. Paste the `.ics` URL.

## Sharing

Share this URL:

```text
https://ec5987.github.io/saprissa-calendar/saprissa.ics
```

Anyone using Apple Calendar, Google Calendar, Outlook, Fantastical, or another iCal-compatible app should be able to subscribe to that same feed.

## GitHub Pages Setup

The included workflow deploys the `public/` folder using GitHub Pages.

In the GitHub repo:

1. Go to `Settings` > `Pages`.
2. Set `Build and deployment` source to `GitHub Actions`.
3. Run the `Update Saprissa calendar` workflow manually once, or wait for the schedule.

The workflow also commits changes to `data/matches.json` and `public/saprissa.ics` when the scraper detects an update.

## Schedule

The workflow runs hourly and can also be started manually from the GitHub Actions tab.

The calendar does not publish live score changes during a match. Final-score fallback checks wait several hours after kickoff before using AiScore, which keeps the feed useful without turning it into a live match tracker.

Scheduled runs only deploy GitHub Pages when the generated match data or calendar feed changes. Manual runs always deploy Pages, which is useful for the first publish after enabling GitHub Pages.
