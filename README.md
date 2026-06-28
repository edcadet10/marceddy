<div align="center">

<img src="assets/banner.svg" alt="MarcEddy — does the boring half of your job hunt" width="100%">

<br/>

[![CI](https://github.com/edcadet10/marceddy/actions/workflows/ci.yml/badge.svg)](https://github.com/edcadet10/marceddy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-7c3aed.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20|%203.11%20|%203.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-34d399)](#quick-start)
[![Mode](https://img.shields.io/badge/mode-dry--run%20by%20default-22d3ee)](#where-it-draws-the-line)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-a78bfa.svg)](https://github.com/edcadet10/marceddy/pulls)

</div>

---

**A job hunt has a boring half and a human half. MarcEddy does the boring half.**

It digs up real openings, works out which ones actually fit you, and remembers everything you've already seen and applied to. Put it on a schedule and it runs on its own, keeping a record as it goes.

> [!IMPORTANT]
> **MarcEddy does not apply to jobs for you.** It finds, scores, and organizes so you can move fast — sending anything is still your call. Here's exactly [where it draws the line](#where-it-draws-the-line).

## What a run does

```mermaid
flowchart LR
    A([Pull fresh openings]) --> B([Score vs your real resume])
    B --> C([Draft a tailored resume])
    C --> D([Skip what you've seen])
    D --> E([Track replies + email a digest])
    E --> F([Learn from your outcomes])

    classDef step fill:#1e1b4b,stroke:#a78bfa,stroke-width:2px,color:#e0e7ff;
    classDef done fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#d1fae5;
    class A,B,C,D,E step;
    class F done;
```

Each time it fires, MarcEddy:

- 🔎 **Pulls fresh openings** from public job APIs, company career pages, and a couple of RSS feeds (full list below).
- 🎯 **Scores each one against your real resume,** so a help-desk role and a senior SRE role don't get measured the same way.
- 📝 **Drafts a tailored resume** for anything that clears your bar — only by reordering and emphasizing what's already true about you, never by inventing a skill you don't have.
- 🧹 **Skips what you've already seen,** so the hourly run doesn't keep surfacing the same five jobs.
- 📬 **Tracks replies.** It watches your inbox, keeps a status for each application, and emails you a digest.
- 🧠 **Learns from results.** Feed it outcomes and it tunes how it matches.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .                 # add ".[dev]" to run the tests
marceddy init
marceddy scan --source us --query "help desk" --limit 20
```

> [!NOTE]
> The core has **no third-party dependencies** — it runs on the Python standard library, and the test suite passes on a bare `pip install -e ".[dev]"`. Two optional extras add more:

```bash
pip install -e ".[docx]"      # write tailored resumes as .docx (otherwise .txt)
pip install -e ".[browser]"   # autofill + the companies-browser ATS source
playwright install chromium   # one-time browser download, browser extra only
```

## Where it draws the line

I wanted something I could leave running without wondering whether it was doing something dumb or sketchy on my behalf. So the limits are deliberate, not afterthoughts.

> [!WARNING]
> **It won't submit applications.** Applying (and creating accounts) sits behind a `--submit` flag that's off by default and never set by the cron job, gated again by `submit.enabled: true` in your local credentials. Even with all of that on, submission is a deliberate no-op in this build.

- 🔒 **It barely touches your email.** Status tracking reads message headers only: From, Subject, Date. It never reads, prints, or logs a message body. The real-mailbox check gives you a count and nothing else.
- 🗝️ **Your secrets stay yours.** Credentials live in `~/.marceddy/credentials.json` (chmod 600), ship as placeholders, and any secret-looking value is redacted before it's printed.
- ✍️ **It won't pad your resume.** Tailoring only selects and reorders what's already in your profile. If it isn't true about you, it doesn't show up.
- 🤝 **It plays by the rules.** The default live source is a public API that permits it in robots.txt, and it never hits an apply endpoint. Optional sources are credited per their terms. Official APIs first, scraping last.
- 📨 **Digests go to your address, and only yours.**

## Job sources

Pick one with `scan --source <name>` (or `search --source <name>` for a quick smoke test). Most need no key.

<details open>
<summary><b>All 20 sources</b> — tap to collapse</summary>

<br/>

| Source | Auth | What it is |
| --- | :---: | --- |
| `fixture` | — | Offline sample data for tests and demos. |
| `arbeitnow` | — | The default live API. Robots-clean, no apply paths. |
| `remotive` | — | Optional; credited per Remotive's terms. |
| `remoteok` | — | RemoteOK's public API. |
| `jobicy` | — | Jobicy's public API (remote roles). |
| `muse` | — | The Muse's public API. |
| `greenhouse` | — | Public Greenhouse job boards. |
| `simplyhired` | — | SimplyHired search, read from the page's own embedded JSON (title, company, location, listed salary). |
| `himalayas` | — | Himalayas API. Remote, often US-eligible, usually with pay listed. |
| `workingnomads` | — | Working Nomads API (remote roles). |
| `weworkremotely` | — | We Work Remotely's RSS feed (remote roles). |
| `devitjobs` | — | DevITjobs US API — US software/IT roles, usually with listed salary. |
| `fourdayweek` | — | 4 Day Week API — roles with a four-day work week. |
| `usajobs` | 🔑 key | USAJOBS — the official US **federal** government jobs API. Free key. |
| `careeronestop` | 🔑 key | CareerOneStop — US Dept. of Labor job postings (National Labor Exchange). Free token. |
| `jsearch` | 🔑 key | JSearch / Google-for-Jobs; pulls in Indeed and LinkedIn too. Needs a RapidAPI key. |
| `indeed` | 🔌 bridge | Reads a live-Indeed inbox dropped in by a small `claude -p` helper. |
| `companies` | — | A curated company→ATS list, queried against each employer's public ATS API (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday, Oracle). |
| `companies-browser` | — | Headless-browser harvest for ATSs with no clean JSON board (Phenom, Taleo, SuccessFactors). |
| `us` | mixed | **The everything-source:** runs all the legitimate US feeds above in one sweep and dedupes. |

</details>

<details>
<summary><b>Keyed sources — getting the free keys</b></summary>

<br/>

All keyed sources **no-op cleanly until a key is present**, so the `us` sweep works with zero config and simply gets richer as you add keys. Drop credentials into `~/.marceddy/credentials.json` under `job_sources`, or set them in the environment.

| Source | Get the key | credentials.json | Environment |
| --- | --- | --- | --- |
| `usajobs` | [developer.usajobs.gov/apirequest](https://developer.usajobs.gov/apirequest) (free, instant) | `job_sources.usajobs.{api_key, email}` | `USAJOBS_API_KEY`, `USAJOBS_EMAIL` |
| `careeronestop` | [careeronestop.org/Developers/WebAPI](https://www.careeronestop.org/Developers/WebAPI/registration.aspx) (free) | `job_sources.careeronestop.{token, user_id}` | `CAREERONESTOP_TOKEN`, `CAREERONESTOP_USERID` |
| `jsearch` | [rapidapi.com/.../jsearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) (free tier) | `job_sources.jsearch.api_key` | `JSEARCH_API_KEY` |

For USAJOBS the registered **email is sent as the User-Agent**, which the API requires.

</details>

## Commands

<details>
<summary><b>Full command reference</b></summary>

<br/>

```text
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

</details>

## Running it on a schedule

One cron line does it. The run is dry by default (no `--submit`) and idempotent: the seen-store means you won't get re-pinged about jobs you've already been shown.

```cron
0 * * * * .../marceddy --home ~/.marceddy scan --source us --query "help desk"
```

> [!TIP]
> Running MarcEddy on two machines? Set `MARCEDDY_INSTANCE=ed-home` (or any label) so each box tags its digest emails — `[ed-home] MarcEddy — 3 new job(s)` — and you can tell them apart at a glance.

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

<div align="center">
<br/>
<sub>Built to do the tedious part, so you can spend your energy on the part that needs a human.</sub>
</div>
