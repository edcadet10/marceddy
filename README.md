# MarcEddy

A fully autonomous job-application agent. **Dry-run by default.**

MarcEddy: searches real job sources → scores each opening against the user's
*true* resume → tailors a resume per role → dedups what it has already seen →
keeps a ledger → tracks application status from email → produces a status
digest → and improves its own matching policy from recorded outcomes.

## Safety / ethics

- **No auto-submit.** Real application submission and account creation sit
  behind an explicit `--submit` flag that is **OFF by default**, never set by
  the hourly schedule, and additionally requires `submit.enabled: true` in the
  local credentials store. Even then, submission is a deliberate no-op in this
  build.
- **Privacy.** Email tracking reads only message *headers* (From/Subject/Date).
  Bodies are never parsed, printed, or logged. The real-mailbox smoke test
  prints only a message *count*.
- **Secrets.** Credentials live in `~/.marceddy/credentials.json` at `chmod 600`,
  holding placeholders by default; any secret value is redacted when shown.
- **No fabrication.** Tailoring only reorders/emphasizes content already in the
  master profile; it never invents skills or experience.
- **ToS / robots.** Default live source is the Arbeitnow public API (robots
  permits it; we never hit auto-apply paths). Remotive is optional and
  attributed per its terms. Prefer official APIs.
- **Digests** are emailed only to the user's own address.

## Install

```
python -m venv .venv && . .venv/bin/activate
pip install -e .            # or: pip install -e ".[dev]" for the test suite
marceddy --help
```

No required third-party dependencies — the core runs on the Python standard
library. The optional browser harvester uses Playwright; install it only if you
want the `companies-browser` source (`pip install playwright && playwright install chromium`).

## Job sources

Select any with `scan --source <name>` / `search --source <name>`:

| Source | Auth | Notes |
| --- | --- | --- |
| `fixture` | none | Offline deterministic fixture (tests / demos). |
| `arbeitnow` | none | Default live API; robots-clean, no auto-apply paths. |
| `remotive` | none | Optional; attributed per Remotive's terms. |
| `remoteok` | none | RemoteOK public API. |
| `jobicy` | none | Jobicy public API (remote jobs). |
| `muse` | none | The Muse public API. |
| `greenhouse` | none | Greenhouse public job boards. |
| `simplyhired` | none | SimplyHired search; reads the page's own `__NEXT_DATA__` JSON (title/company/location/listed salary). |
| `himalayas` | none | Himalayas public API (remote, often US-eligible; listed salary). |
| `workingnomads` | none | Working Nomads public API (remote jobs). |
| `weworkremotely` | none | We Work Remotely RSS feed (remote jobs). |
| `jsearch` | API key | JSearch / Google-for-Jobs (adds Indeed & LinkedIn); needs a RapidAPI key. |
| `indeed` | bridge | Reads a live-Indeed inbox dropped by a small `claude -p` bridge. |
| `companies` | none | Curated employer→ATS registry pulled directly from each company's ATS public API (Greenhouse/Lever/Ashby/SmartRecruiters/Workable/Workday/Oracle). |
| `companies-browser` | none | Headless-browser harvest for ATSs without a clean JSON board (Phenom/Taleo/SuccessFactors). |
| `us` | mixed | Aggregates all of the legitimate US sources above into one sweep. |

## CLI

```
marceddy --help
marceddy init
marceddy scan      [--source us|arbeitnow|simplyhired|companies|...] [--query Q] [--limit N] [--no-tailor] [--submit]
marceddy report    [--email]
marceddy learn     [--outcomes outcomes.json]
marceddy search    [--source <name>] [--query Q] [--limit N]   # live smoke test
marceddy companies [--check]                                   # list the employer registry (and live job counts)
marceddy email-scan [--mailbox DIR] [--real]
marceddy creds
```

## Hourly schedule

Installed via cron, dry-run (no `--submit`), idempotent (seen-store):

```
0 * * * * .../marceddy --home ~/.marceddy scan --source arbeitnow --query support
```
