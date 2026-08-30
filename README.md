# Saprissa - Calendario

A small, dependency-free Python project that publishes a subscribable iCal feed for Deportivo Saprissa matches.

The official schedule source is:

https://www.saprissa.com/calendario

Official completed results are read from:

https://www.saprissa.com/resultados

If a match has already started and Saprissa's pages do not have a score yet, missing scores are enriched on a best-effort basis from:

https://www.aiscore.com/team-deportivo-saprissa/o17pji0p20i27jw

## Files

```text
data/matches.json        Stored match data
public/saprissa.ics      Public calendar feed
public/index.html        Small GitHub Pages entry page
scripts/update.py        Scraper, optional score enrichment, and ICS generator
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

To write outputs somewhere else:

```bash
python3 scripts/update.py --data-file /tmp/matches.json --ics-file /tmp/saprissa.ics
```

## Calendar Behavior

- Match times are stored as Costa Rica time: `America/Costa_Rica`.
- Calendar apps should convert the event time to each subscriber's local time zone.
- Matches with unknown times are emitted as all-day placeholder events.
- Event titles use the format `Home Team - Away Team`.
- Completed matches include the score when available, like `Home Team - Away Team (2-1)`.
- Future fixtures come from the official Saprissa calendar.
- Completed men's matches from July 1, 2026 onward come from Saprissa's official results page.
- AiScore is only used as a fallback when Saprissa is missing a score for a match that has already started.
- Past matches already stored in `data/matches.json` are preserved so scores can still be added after they leave the official schedule page.

## Apple Calendar Subscription

Once GitHub Pages is enabled, the public feed URL should be:

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

## Sharing Later

After the repository is pushed to GitHub and Pages is enabled, share this URL:

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

There is also a 5-minute scheduled check. That run exits early unless stored match data says a match is within 30 minutes before kickoff through 6 hours after kickoff. During that window, the updater can use AiScore as a fallback if Saprissa has not published the score yet. The wider window gives delayed matches more room to update without scraping frequently on normal non-match days.

Scheduled runs only deploy GitHub Pages when the generated match data or calendar feed changes. Manual runs always deploy Pages, which is useful for the first publish after enabling GitHub Pages.
