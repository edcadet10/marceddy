# MarcEddy

[![CI](https://github.com/edcadet10/marceddy/actions/workflows/ci.yml/badge.svg)](https://github.com/edcadet10/marceddy/actions/workflows/ci.yml)

MarcEddy is a job-search agent that handles the tedious half of a job hunt:
finding real openings, figuring out which ones are actually worth your time, and
keeping track of what you've already seen and applied to. It runs on a schedule
and leaves a paper trail.

One thing up front: **it does not apply to jobs for you.** It finds, scores, and
organizes — you stay in the loop for anything that goes out the door. See
[Where it draws the line](#where-it-draws-the-line) below.

## What a run actually does

Each time it runs, MarcEddy:

1. Pulls openings from a mix of sources — public job APIs, company career pages,
   and a couple of RSS feeds (full list [below](#job-sources)).
2. Scores every opening against your *real* resume, so a help-desk role and a
   senior SRE role don't get treated as the same fit.
3. Writes a tailored resume for the roles that clear the bar — but only ever by
   reordering and emphasizing things you already have. It never makes up skills
   or experience.
4. Ignores anything it has shown you before, so the hourly run isn't constantly
   re-surfacing the same five jobs.
5. Watches your inbox for replies and keeps a running status for each
   application, then emails you a digest.
6. Adjusts its own matching over time from outcomes you feed back to it.

## Quick start

```
python -m venv .venv && . .venv/bin/activate
pip install -e .                 # add ".[dev]" if you want to run the tests
marceddy init
marceddy scan --source us --query "help desk" --limit 20
```

The core has **no third-party dependencies** — it runs on the Python standard
library. The one optional extra is Playwright, and only if you want the
browser-based source (`companies-browser`):

```
pip install playwright && playwright install chromium
```

## Where it draws the line

I wanted something I could leave running without worrying about it doing
something dumb or sketchy on my behalf. So:

- **It won't submit applications.** Actually applying (and creating accounts)
  lives behind a `--submit` flag that's off by default, never set by the cron
  job, and gated again by `submit.enabled: true` in your local credentials. Even
  with all of that, submission is a deliberate no-op in this build.
- **It barely touches your email.** Status tracking reads message *headers*
  only — From, Subject, Date. It never parses, prints, or logs a message body.
  The real-mailbox check prints a count and nothing else.
- **Your secrets stay yours.** Credentials live in
  `~/.marceddy/credentials.json` (chmod 600), default to placeholders, and any
  secret-looking value is redacted whenever something gets printed.
- **It doesn't pad your resume.** Tailoring only selects and reorders what's
  already in your profile. If it isn't true about you, it won't show up.
- **It plays by the rules.** The default live source is a public API whose
  robots.txt permits it, and it never hits apply endpoints. Optional sources are
  attributed per their terms. Official APIs first, scraping last.
- **Digests only go to you** — your own address, no one else's.

## Job sources

Pick one with `scan --source <name>` (or `search --source <name>` for a quick
smoke test). Most need no key at all:

| Source | Auth | What it is |
| --- | --- | --- |
| `fixture` | none | Offline sample data, used by the tests and demos. |
| `arbeitnow` | none | The default live API. Robots-clean, no apply paths. |
| `remotive` | none | Optional; attributed per Remotive's terms. |
| `remoteok` | none | RemoteOK's public API. |
| `jobicy` | none | Jobicy's public API (remote roles). |
| `muse` | none | The Muse's public API. |
| `greenhouse` | none | Public Greenhouse job boards. |
| `simplyhired` | none | SimplyHired search, read straight from the page's own embedded JSON (title, company, location, listed salary). |
| `himalayas` | none | Himalayas API — remote, frequently US-eligible, with listed pay. |
| `workingnomads` | none | Working Nomads API (remote roles). |
| `weworkremotely` | none | We Work Remotely's RSS feed (remote roles). |
| `jsearch` | API key | JSearch / Google-for-Jobs — pulls in Indeed and LinkedIn too. Needs a RapidAPI key. |
| `indeed` | bridge | Reads a live-Indeed inbox dropped in by a small `claude -p` helper. |
| `companies` | none | A curated company→ATS list, queried directly against each employer's public ATS API (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday, Oracle). |
| `companies-browser` | none | Headless-browser harvest for ATSs with no clean JSON board (Phenom, Taleo, SuccessFactors). |
| `us` | mixed | The everything-source: runs all of the legitimate US feeds above in one sweep and dedupes the result. |

## Commands

```
marceddy --help
marceddy init                                                  # set up the home dir
marceddy scan      [--source us|arbeitnow|simplyhired|...] [--query Q] [--limit N] [--no-tailor] [--submit]
marceddy report    [--email]                                   # status digest
marceddy learn     [--outcomes outcomes.json]                  # update matching from results
marceddy search    [--source <name>] [--query Q] [--limit N]   # live source smoke test
marceddy companies [--check]                                   # list the employer registry (with live job counts)
marceddy email-scan [--mailbox DIR] [--real]
marceddy creds
```

## Running it on a schedule

A cron line is all it takes. It's dry-run (no `--submit`) and idempotent — the
seen-store means it won't re-send jobs you've already been shown:

```
0 * * * * .../marceddy --home ~/.marceddy scan --source us --query "help desk"
```

## Tests

```
pip install -e ".[dev]"
pytest -q
```
