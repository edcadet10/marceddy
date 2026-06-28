"""Job sources.

- FixtureSource: deterministic, offline. Used for tests and the reproducible
  scan/idempotency demo (no network flakiness in a determinism proof).
- ArbeitnowSource: live, free public job-board API. robots.txt allows the API
  path; it disallows ``/jobs/companies/*/apply`` which we never touch (we never
  auto-apply). This is the default LIVE source.
- RemotiveSource: live, optional. Remotive's API terms forbid republishing and
  email-harvesting, so it is NOT the default; when used we attribute the source
  and link back, per their terms.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .models import Job, slugify

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}


US_STATE_NAMES = {
    "ALABAMA", "ALASKA", "ARIZONA", "ARKANSAS", "CALIFORNIA", "COLORADO",
    "CONNECTICUT", "DELAWARE", "FLORIDA", "GEORGIA", "HAWAII", "IDAHO",
    "ILLINOIS", "INDIANA", "IOWA", "KANSAS", "KENTUCKY", "LOUISIANA", "MAINE",
    "MARYLAND", "MASSACHUSETTS", "MICHIGAN", "MINNESOTA", "MISSISSIPPI",
    "MISSOURI", "MONTANA", "NEBRASKA", "NEVADA", "NEW HAMPSHIRE", "NEW JERSEY",
    "NEW MEXICO", "NEW YORK", "NORTH CAROLINA", "NORTH DAKOTA", "OHIO",
    "OKLAHOMA", "OREGON", "PENNSYLVANIA", "RHODE ISLAND", "SOUTH CAROLINA",
    "SOUTH DAKOTA", "TENNESSEE", "TEXAS", "UTAH", "VERMONT", "VIRGINIA",
    "WASHINGTON", "WEST VIRGINIA", "WISCONSIN", "WYOMING",
    "DISTRICT OF COLUMBIA",
}


def _is_us(location):
    """True if a free-text location looks US-based (state code/name, USA, etc.)."""
    s = (location or "").upper()
    if not s:
        return False
    if "UNITED STATES" in s or "USA" in s or "U.S." in s:
        return True
    if re.search(r"\bUS\b", s):  # trailing country marker, e.g. "Columbus, OH, US"
        return True
    if any(name in s for name in US_STATE_NAMES):  # JSearch uses full state names
        return True
    return any(tok in US_STATES for tok in re.findall(r"\b([A-Z]{2})\b", s))


_FOREIGN = ("brazil", "são", "sao paulo", "latin america", "europe", "germany",
            "india", "canada", "united kingdom", "philippines", "argentina",
            "mexico", "belo horizonte", "porto alegre", "florian", "campinas")


def _remote_ok(location):
    """For a remote job, True only if US-eligible (not pinned to a foreign region)."""
    s = (location or "").lower()
    if not s:
        return True
    if any(f in s for f in _FOREIGN):
        return False
    if any(t in s for t in ("anywhere", "worldwide", "global", "united states",
                            "usa", "u.s.", "us only", "north america", "americas",
                            "remote")):
        return True
    return _is_us(location)

def _is_foreign(location):
    """True only when a location clearly names a non-US country/region. Used by
    the curated company registry, where a blank/ambiguous location (e.g. a
    Workday facility name) should be KEPT, not dropped."""
    return any(f in (location or "").lower() for f in _FOREIGN)

PKG_DIR = Path(__file__).resolve().parent
FIXTURE_JOBS = PKG_DIR / "data" / "jobs_fixture.json"

USER_AGENT = "MarcEddy/0.1 (personal job-search agent; +https://github.com/edcadet10/marceddy)"


class JobSource:
    name = "base"
    attribution = ""

    def fetch(self, query="", limit=25):
        raise NotImplementedError


class FixtureSource(JobSource):
    name = "fixture"
    attribution = "Local deterministic fixture (offline)."

    def __init__(self, path=None):
        self.path = Path(path) if path else FIXTURE_JOBS

    def fetch(self, query="", limit=25):
        data = json.loads(self.path.read_text())
        jobs = []
        for d in data:
            jobs.append(Job(
                source="fixture", company=d["company"], title=d["title"], url=d["url"],
                location=d.get("location", ""), remote=bool(d.get("remote", False)),
                description=d.get("description", ""), tags=d.get("tags", []),
                posted_ts=d.get("posted_ts", ""), ext_id=str(d.get("id", "")),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


def _http_get_json(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _http_get_json_auth(url, headers, timeout=25):
    """Like _http_get_json but merges caller headers (for keyed APIs)."""
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _http_post_json(url, payload, timeout=20):
    """POST a JSON body and parse a JSON response (Workday's cxs API needs this)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _http_get_text(url, timeout=25):
    """GET raw text via urllib (for RSS/XML feeds that have no JSON endpoint)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _http_get_text_curl(url, user_agent, timeout=30):
    """GET raw page text via the ``curl`` binary instead of urllib.

    Some sites (notably SimplyHired, fronted by Cloudflare) block Python's urllib
    on its TLS/JA3 fingerprint with a 403 even when the headers look browser-like,
    yet serve curl's request fine. We shell out so the source still works from the
    home server. Returns "" on any failure (missing curl, non-zero exit, timeout)
    so a dead source is a clean no-op and never sinks the sweep.
    """
    import subprocess
    try:
        p = subprocess.run(
            ["curl", "-s", "-S", "-L", "--compressed", "-A", user_agent,
             "--max-time", str(int(timeout)), url],
            capture_output=True, text=True, timeout=timeout + 5)
        return p.stdout or "" if p.returncode == 0 else ""
    except Exception:
        return ""


def _marceddy_home():
    return Path(os.environ.get("MARCEDDY_HOME") or os.path.expanduser("~/.marceddy"))


def _jsearch_key():
    """RapidAPI key for JSearch, from env or the credentials store.

    Order: env JSEARCH_API_KEY / RAPIDAPI_KEY, then
    <MARCEDDY_HOME or ~/.marceddy>/credentials.json -> job_sources.jsearch.api_key.
    Returns "" when unset, so JSearchSource cleanly no-ops until a key is added.
    """
    for var in ("JSEARCH_API_KEY", "RAPIDAPI_KEY"):
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip()
    p = _marceddy_home() / "credentials.json"
    if p.exists():
        try:
            data = json.loads(p.read_text())
            return ((data.get("job_sources", {}) or {}).get("jsearch", {})
                    or {}).get("api_key", "").strip()
        except Exception:
            return ""
    return ""


def _usajobs_creds():
    """(api_key, email) for the USAJOBS API, from env or the credentials store.

    Env USAJOBS_API_KEY (+ USAJOBS_EMAIL for the required User-Agent), else
    credentials.json -> job_sources.usajobs.{api_key,email}. Returns ("","") when
    unset so USAJobsSource cleanly no-ops until a key is dropped in.
    """
    key = (os.environ.get("USAJOBS_API_KEY") or "").strip()
    email = (os.environ.get("USAJOBS_EMAIL") or "").strip()
    if not (key and email):
        p = _marceddy_home() / "credentials.json"
        if p.exists():
            try:
                uj = ((json.loads(p.read_text()).get("job_sources", {}) or {})
                      .get("usajobs", {}) or {})
                key = key or (uj.get("api_key") or "").strip()
                email = email or (uj.get("email") or "").strip()
            except Exception:
                pass
    return key, email


def _careeronestop_creds():
    """(token, user_id) for the CareerOneStop API, from env or the credentials store.

    Env CAREERONESTOP_TOKEN + CAREERONESTOP_USERID, else credentials.json ->
    job_sources.careeronestop.{token,user_id}. Returns ("","") when unset so
    CareerOneStopSource cleanly no-ops until both are provided.
    """
    token = (os.environ.get("CAREERONESTOP_TOKEN") or "").strip()
    uid = (os.environ.get("CAREERONESTOP_USERID") or "").strip()
    if not (token and uid):
        p = _marceddy_home() / "credentials.json"
        if p.exists():
            try:
                co = ((json.loads(p.read_text()).get("job_sources", {}) or {})
                      .get("careeronestop", {}) or {})
                token = token or (co.get("token") or "").strip()
                uid = uid or (co.get("user_id") or "").strip()
            except Exception:
                pass
    return token, uid


class ArbeitnowSource(JobSource):
    name = "arbeitnow"
    attribution = ("Jobs via Arbeitnow public job-board API (arbeitnow.com). "
                   "Free developer API; robots.txt permits the API path.")
    BASE = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE)
        items = data.get("data", []) if isinstance(data, dict) else []
        jobs = []
        for d in items:
            jobs.append(Job(
                source="arbeitnow",
                company=(d.get("company_name") or "Unknown").strip(),
                title=(d.get("title") or "").strip(),
                url=d.get("url", ""),
                location=d.get("location", "") or "",
                remote=bool(d.get("remote")),
                description=(d.get("description", "") or "")[:2000],
                tags=d.get("tags", []) or [],
                posted_ts=str(d.get("created_at", "")),
                ext_id=d.get("slug", ""),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class RemotiveSource(JobSource):
    name = "remotive"
    attribution = ("Jobs via Remotive (remotive.com), source attributed and linked back "
                   "per Remotive API terms. Not for republication or email-harvesting.")
    BASE = "https://remotive.com/api/remote-jobs"

    def fetch(self, query="", limit=25):
        url = self.BASE
        if query:
            url += "?search=" + urllib.parse.quote(query)
        data = _http_get_json(url)
        items = data.get("jobs", []) if isinstance(data, dict) else []
        jobs = []
        for d in items:
            jobs.append(Job(
                source="remotive",
                company=(d.get("company_name") or "Unknown").strip(),
                title=(d.get("title") or "").strip(),
                url=d.get("url", ""),
                location=d.get("candidate_required_location", "") or "",
                remote=True,
                description=(d.get("description", "") or "")[:2000],
                tags=d.get("tags", []) or [],
                posted_ts=str(d.get("publication_date", "")),
                ext_id=str(d.get("id", "")),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class MuseSource(JobSource):
    """The Muse public API — US-focused 'Computer and IT' postings, no key."""
    name = "muse"
    attribution = "Jobs via The Muse public API (themuse.com)."
    BASE = "https://www.themuse.com/api/public/jobs"
    PAGES = 3  # ~60 listings/run

    def fetch(self, query="", limit=25):
        jobs = []
        for page in range(self.PAGES):
            url = (self.BASE + "?category=" + urllib.parse.quote("Computer and IT")
                   + "&page=%d" % page)
            try:
                data = _http_get_json(url)
            except Exception:
                break
            for d in data.get("results", []):
                locs = [l.get("name", "") for l in d.get("locations", [])]
                comp = (d.get("company") or {}).get("name") or "Unknown"
                jobs.append(Job(
                    source="muse", company=comp.strip(),
                    title=(d.get("name") or "").strip(),
                    url=(d.get("refs") or {}).get("landing_page", ""),
                    location=", ".join(locs),
                    remote=any("remote" in l.lower() or "flexible" in l.lower() for l in locs),
                    description="",
                    tags=[(c.get("name") or "") for c in d.get("categories", [])],
                    posted_ts=str(d.get("publication_date", "")),
                    ext_id=str(d.get("id", "")),
                ))
            if page + 1 >= data.get("page_count", 1):
                break
        jobs = [j for j in jobs if j.remote or _is_us(j.location)]
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class GreenhouseSource(JobSource):
    """Pull straight from company career pages via their public Greenhouse boards.

    Each token is a real US employer's job board. No auth, ToS-clean (this is the
    same API public job-board aggregators are invited to use).
    """
    name = "greenhouse"
    attribution = "Jobs pulled directly from company career pages (public Greenhouse boards)."
    BASE = "https://boards-api.greenhouse.io/v1/boards/%s/jobs"
    BOARDS = [
        "databricks", "stripe", "gitlab", "cloudflare", "robinhood", "coinbase",
        "doordash", "dropbox", "reddit", "samsara", "gusto", "benchling", "lyft",
        "instacart", "brex", "figma", "datadog", "snowflake", "mongodb", "confluent",
        "elastic", "twilio", "retool", "sofi", "affirm", "chime", "webflow",
        "grammarly", "unity", "pinterest", "discord", "twitch",
    ]

    def fetch(self, query="", limit=25):
        jobs, scanned = [], 0
        for token in self.BOARDS:
            if scanned >= 20:
                break
            try:
                data = _http_get_json(self.BASE % token, timeout=12)
            except Exception:
                continue
            scanned += 1
            disp = token.replace("-", " ").title()
            for d in data.get("jobs", []):
                loc = (d.get("location") or {}).get("name", "")
                jobs.append(Job(
                    source="greenhouse", company=disp,
                    title=(d.get("title") or "").strip(),
                    url=d.get("absolute_url", ""), location=loc,
                    remote=("remote" in loc.lower()), description="", tags=[],
                    posted_ts=str(d.get("updated_at", "")),
                    ext_id="%s-%s" % (token, d.get("id", "")),
                ))
            if len([j for j in jobs if j.remote or _is_us(j.location)]) >= limit * 4:
                break  # enough US matches; stop hitting more boards
        jobs = [j for j in jobs if j.remote or _is_us(j.location)]
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class RemoteOKSource(JobSource):
    """RemoteOK public API — high-churn remote jobs, no key."""
    name = "remoteok"
    attribution = "Jobs via RemoteOK public API (remoteok.com)."
    BASE = "https://remoteok.com/api"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE)
        items = [d for d in data if isinstance(d, dict) and d.get("company")
                 and (d.get("position") or d.get("title"))] if isinstance(data, list) else []
        jobs = []
        for d in items:
            jobs.append(Job(
                source="remoteok",
                company=(d.get("company") or "Unknown").strip(),
                title=(d.get("position") or d.get("title") or "").strip(),
                url=d.get("url", "") or ("https://remoteok.com/l/" + str(d.get("id", ""))),
                location=d.get("location", "") or "",
                remote=True,
                description=(d.get("description", "") or "")[:2000],
                tags=d.get("tags", []) or [],
                posted_ts=str(d.get("date", "")),
                ext_id=str(d.get("id", "")),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class JobicySource(JobSource):
    """Jobicy public API — remote jobs, no key."""
    name = "jobicy"
    attribution = "Jobs via Jobicy public API (jobicy.com)."
    BASE = "https://jobicy.com/api/v2/remote-jobs"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE + "?count=50")
        items = data.get("jobs", []) if isinstance(data, dict) else []
        jobs = []
        for d in items:
            jobs.append(Job(
                source="jobicy",
                company=(d.get("companyName") or "Unknown").strip(),
                title=(d.get("jobTitle") or "").strip(),
                url=d.get("url", "") or "",
                location=d.get("jobGeo", "") or "",
                remote=True,
                description=(d.get("jobExcerpt", "") or "")[:2000],
                tags=[d.get("jobIndustry")] if d.get("jobIndustry") else [],
                posted_ts=str(d.get("pubDate", "")),
                ext_id=str(d.get("id", "")),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class SimplyHiredSource(JobSource):
    """SimplyHired search results (simplyhired.com).

    SimplyHired server-renders each results page and embeds the full listing as
    JSON in a ``__NEXT_DATA__`` script tag, so we read the page's own data rather
    than scraping the DOM -- title, company, location and the LISTED salary all
    come straight from that JSON. Cloudflare blocks urllib's TLS fingerprint, so
    the fetch goes through the curl binary (see ``_http_get_text_curl``).

    Location defaults to Columbus, OH (Ed's market) and is overridable via the
    MARCEDDY_SIMPLYHIRED_LOCATION env var. A missing curl / block / parse failure
    yields [] -- a clean no-op, like every other live source here.
    """
    name = "simplyhired"
    attribution = ("Jobs via SimplyHired search (simplyhired.com); the results page's "
                   "own __NEXT_DATA__ JSON is read for title/company/location/salary.")
    BASE = "https://www.simplyhired.com/search"
    DEFAULT_LOCATION = "Columbus, OH"
    BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

    def _location(self):
        return os.environ.get("MARCEDDY_SIMPLYHIRED_LOCATION", self.DEFAULT_LOCATION)

    def fetch(self, query="", limit=25):
        params = {"l": self._location()}
        if query:
            params["q"] = query
        url = self.BASE + "?" + urllib.parse.urlencode(params)
        html = _http_get_text_curl(url, self.BROWSER_UA)
        # SimplyHired's `q=` param already does server-side relevance ranking, so we
        # do NOT re-filter on a literal substring here (the matched term often lives
        # in the full posting, not the truncated card snippet we receive).
        return self._parse(html)[:limit]

    def _parse(self, html):
        """Pull the jobs list out of the page's __NEXT_DATA__ JSON. Pure/offline so
        it can be unit-tested against a captured fixture with no network."""
        if not html:
            return []
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.S)
        if not m:
            return []
        try:
            raw = json.loads(m.group(1))["props"]["pageProps"]["jobs"]
        except Exception:
            return []
        jobs = []
        for d in raw:
            if not isinstance(d, dict):
                continue
            title = (d.get("title") or "").strip()
            if not title:
                continue
            bot = d.get("botUrl") or ""
            url = ("https://www.simplyhired.com" + bot) if bot.startswith("/") else bot
            loc = (d.get("location") or "").strip()
            salary = (d.get("salaryInfo") or "").strip()
            jobs.append(Job(
                source="simplyhired",
                company=(d.get("company") or "Unknown").strip(),
                title=title,
                url=url,
                location=loc,
                remote=bool(d.get("remoteAttributes")) or ("remote" in loc.lower()),
                description=(d.get("snippet") or "")[:2000],
                tags=[t for t in (d.get("jobTypes") or []) if isinstance(t, str)],
                posted_ts=str(d.get("dateOnIndeed", "") or ""),
                ext_id=str(d.get("jobKey") or ""),
                salary=salary,
                salary_basis="listed" if salary else "",
            ))
        return jobs


class HimalayasSource(JobSource):
    """Himalayas public API — remote jobs, no key. Often US-eligible."""
    name = "himalayas"
    attribution = "Jobs via the Himalayas public API (himalayas.app)."
    BASE = "https://himalayas.app/jobs/api"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE + "?limit=100")
        items = data.get("jobs", []) if isinstance(data, dict) else []
        jobs = []
        for d in items:
            if not isinstance(d, dict):
                continue
            title = (d.get("title") or "").strip()
            if not title:
                continue
            loc = ", ".join(x for x in (d.get("locationRestrictions") or []) if x) or "Remote"
            salary = ""
            mn, mx = d.get("minSalary"), d.get("maxSalary")
            cur = (d.get("currency") or "USD")
            per = (d.get("salaryPeriod") or "").strip()
            try:
                if mn and mx:
                    salary = f"{cur} {int(mn):,}-{int(mx):,} {per}".strip()
                elif mn:
                    salary = f"{cur} {int(mn):,}+ {per}".strip()
            except (TypeError, ValueError):
                salary = ""
            jobs.append(Job(
                source="himalayas",
                company=(d.get("companyName") or "Unknown").strip(),
                title=title,
                url=d.get("applicationLink") or d.get("guid") or "",
                location=loc,
                remote=True,
                description=(d.get("description") or "")[:2000],
                tags=[c for c in (d.get("categories") or []) if isinstance(c, str)],
                posted_ts=str(d.get("pubDate") or ""),
                ext_id=str(d.get("guid") or ""),
                salary=salary,
                salary_basis="listed" if salary else "",
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class WorkingNomadsSource(JobSource):
    """Working Nomads public API — remote jobs, no key."""
    name = "workingnomads"
    attribution = "Jobs via the Working Nomads public API (workingnomads.com)."
    BASE = "https://www.workingnomads.com/api/exposed_jobs/"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE)
        items = data if isinstance(data, list) else data.get("jobs", [])
        jobs = []
        for d in items:
            if not isinstance(d, dict):
                continue
            title = (d.get("title") or "").strip()
            if not title:
                continue
            jobs.append(Job(
                source="workingnomads",
                company=(d.get("company_name") or "Unknown").strip(),
                title=title,
                url=d.get("url", "") or "",
                location=(d.get("location") or "Remote").strip(),
                remote=True,
                description=(d.get("description") or "")[:2000],
                tags=[t for t in (d.get("tags") or "").split(",") if t][:8],
                posted_ts=str(d.get("pub_date") or ""),
                ext_id=d.get("url", "") or "",
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class WeWorkRemotelySource(JobSource):
    """We Work Remotely RSS feed — remote jobs, no key. Titles are "Company: Role"."""
    name = "weworkremotely"
    attribution = "Jobs via the We Work Remotely RSS feed (weworkremotely.com)."
    BASE = "https://weworkremotely.com/remote-jobs.rss"

    def fetch(self, query="", limit=25):
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(_http_get_text(self.BASE))
        except Exception:
            return []
        jobs = []
        seen = set()
        for it in root.findall(".//item"):
            def g(tag):
                e = it.find(tag)
                return (e.text or "").strip() if e is not None and e.text else ""
            raw = g("title")
            if not raw:
                continue
            key = g("guid") or raw
            if key in seen:  # WWR's feed repeats featured jobs
                continue
            seen.add(key)
            company, sep, role = raw.partition(":")
            if sep and role.strip():
                comp, title = company.strip(), role.strip()
            else:
                comp, title = "Unknown", raw
            jobs.append(Job(
                source="weworkremotely",
                company=comp or "Unknown",
                title=title,
                url=g("link") or g("guid"),
                location=g("region") or "Remote",
                remote=True,
                description="",
                tags=[g("category")] if g("category") else [],
                posted_ts=g("pubDate"),
                ext_id=g("guid"),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class DevITjobsSource(JobSource):
    """DevITjobs US public API — US software/IT jobs, no key, listed salary."""
    name = "devitjobs"
    attribution = "Jobs via the DevITjobs US public API (devitjobs.us)."
    BASE = "https://devitjobs.us/api/jobsLight"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE)
        items = data if isinstance(data, list) else data.get("jobs", [])
        jobs = []
        for d in items:
            if not isinstance(d, dict):
                continue
            title = (d.get("name") or "").strip()
            if not title:
                continue
            city = (d.get("actualCity") or d.get("cityCategory") or "").replace("-", " ").strip()
            state = (d.get("stateCategory") or "").replace("-", " ").strip()
            loc = ", ".join(x for x in (city, state) if x) or "United States"
            workplace = (d.get("workplace") or "").lower()
            remote = workplace == "remote" or (d.get("remoteType") or "").lower() in ("anywhere", "remote")
            salary = ""
            sf, st = d.get("annualSalaryFrom"), d.get("annualSalaryTo")
            try:
                if sf and st:
                    salary = "$%s-$%s a year" % (format(int(sf), ","), format(int(st), ","))
                elif sf:
                    salary = "$%s+ a year" % format(int(sf), ",")
            except (TypeError, ValueError):
                salary = ""
            slug = d.get("jobUrl") or ""
            url = ("https://devitjobs.us/job/" + slug) if slug else "https://devitjobs.us/"
            jobs.append(Job(
                source="devitjobs",
                company=(d.get("company") or "Unknown").strip(),
                title=title,
                url=url,
                location=loc,
                remote=remote,
                description="",
                tags=[t for t in (d.get("technologies") or []) if isinstance(t, str)][:10],
                posted_ts=str(d.get("activeFrom") or ""),
                ext_id=str(d.get("_id") or ""),
                salary=salary,
                salary_basis="listed" if salary else "",
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class FourDayWeekSource(JobSource):
    """4 Day Week public API — roles with a 4-day work week, no key."""
    name = "fourdayweek"
    attribution = "Jobs via the 4 Day Week public API (4dayweek.io); 4-day-week roles."
    BASE = "https://4dayweek.io/api/jobs"

    def fetch(self, query="", limit=25):
        data = _http_get_json(self.BASE)
        items = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        jobs = []
        for d in items:
            if not isinstance(d, dict):
                continue
            title = (d.get("title") or "").strip()
            if not title:
                continue
            locs = d.get("locations") or []
            loc0 = locs[0] if locs and isinstance(locs[0], dict) else {}
            loc = ", ".join(x for x in (loc0.get("city"), loc0.get("country")) if x) or "Remote"
            arrangement = (d.get("work_arrangement") or "").lower()
            remote = arrangement == "remote" or "remote" in loc.lower()
            slug = d.get("slug") or ""
            url = ("https://4dayweek.io/jobs/" + slug) if slug else "https://4dayweek.io/remote-jobs"
            tags = [t for t in (d.get("category"), d.get("level"), "4-day week") if t]
            jobs.append(Job(
                source="fourdayweek",
                company=(d.get("company_name") or "Unknown").strip(),
                title=title,
                url=url,
                location=loc,
                remote=remote,
                description="",
                tags=tags,
                posted_ts=str(d.get("posted") or ""),
                ext_id=str(d.get("id") or ""),
            ))
        if query:
            q = query.lower()
            jobs = [j for j in jobs if q in j.text_blob()]
        return jobs[:limit]


class IndeedFileSource(JobSource):
    """Indeed jobs fetched via the LIVE Indeed connection.

    MarcEddy's cron can't speak to the claude.ai Indeed MCP directly, but a tiny
    `claude -p` bridge (indeed_pull.sh) can — it calls the Indeed search tool and
    drops the results (with listed salary) as JSON at ~/.marceddy/indeed_inbox.json.
    This source just reads that file, keeping MarcEddy itself stdlib-only. A
    missing / stale / garbled inbox yields [] (clean no-op).
    """
    name = "indeed"
    attribution = "Jobs via the live Indeed connection (indeed.com), refreshed hourly."
    MAX_AGE_MIN = 180  # ignore an inbox older than this so stale pulls don't resurface

    def _path(self):
        return _marceddy_home() / "indeed_inbox.json"

    def fetch(self, query="", limit=25):
        p = self._path()
        try:
            if (time.time() - p.stat().st_mtime) > self.MAX_AGE_MIN * 60:
                return []
            data = json.loads(p.read_text())
        except Exception:
            return []
        jobs = []
        for d in (data if isinstance(data, list) else []):
            if not isinstance(d, dict) or not (d.get("title") and d.get("url")):
                continue
            sal = (d.get("salary") or "").strip()
            loc = (d.get("location") or "").strip()
            jobs.append(Job(
                source="indeed",
                company=(d.get("company") or "Unknown").strip(),
                title=(d.get("title") or "").strip(),
                url=d.get("url", ""),
                location=loc,
                remote=bool(d.get("remote")) or ("remote" in loc.lower()),
                description=(d.get("description", "") or "")[:2000],
                tags=[], posted_ts=str(d.get("posted", "") or ""),
                ext_id=str(d.get("ext_id") or d.get("url") or ""),
                salary=sal, salary_estimated=False,
                salary_basis=("listed on the posting" if sal else ""),
            ))
        if query:
            ql = query.lower()
            jobs = [j for j in jobs if ql in j.text_blob()]
        return jobs[:limit]


class JSearchSource(JobSource):
    """JSearch (RapidAPI) — Google-for-Jobs aggregator that INCLUDES Indeed and
    LinkedIn postings through a sanctioned API (no scraping, no account-ban risk).

    Needs a free RapidAPI key in env JSEARCH_API_KEY / RAPIDAPI_KEY or in
    credentials.json -> job_sources.jsearch.api_key. With no key it returns [] so
    the `us` aggregate keeps working unchanged until a key is dropped in.
    """
    name = "jsearch"
    attribution = ("Jobs via JSearch on RapidAPI (Google for Jobs), which aggregates "
                   "Indeed, LinkedIn and employer career sites. Each result links back "
                   "to its original posting/apply page.")
    BASE = "https://jsearch.p.rapidapi.com/search-v2"
    HOST = "jsearch.p.rapidapi.com"
    # Used when scan runs with an empty query (the hourly `us` sweep does).
    DEFAULT_QUERY = "IT support help desk desktop support technician"
    DATE_POSTED = "week"   # all|today|3days|week|month — bounds the API window
    NUM_PAGES = 1          # 1 page ~= 10 results == 1 request (free-tier friendly)
    # Free RapidAPI tier is 200 calls/month; an hourly cron (~720/mo) would burn
    # it out in ~8 days. Self-throttle the AUTOMATED sweep (empty query) to one
    # call per interval so coverage lasts all month (~180/mo at 240 min). Manual
    # `search --query ...` calls are never throttled. Override via env
    # MARCEDDY_JSEARCH_INTERVAL_MIN (0 = no throttle, e.g. on a paid plan).
    MIN_INTERVAL_MIN = 240

    def _stamp_path(self):
        return _marceddy_home() / ".jsearch_last"

    def _interval_min(self):
        try:
            return int(os.environ.get("MARCEDDY_JSEARCH_INTERVAL_MIN",
                                      self.MIN_INTERVAL_MIN))
        except (TypeError, ValueError):
            return self.MIN_INTERVAL_MIN

    def _throttled(self):
        mins = self._interval_min()
        if mins <= 0:
            return False
        p = self._stamp_path()
        try:
            return (time.time() - float(p.read_text().strip())) < mins * 60
        except Exception:
            return False  # no/garbled stamp -> allow the call

    def _mark_called(self):
        try:
            self._stamp_path().write_text(str(time.time()))
        except Exception:
            pass

    def fetch(self, query="", limit=25):
        key = _jsearch_key()
        if not key:
            return []
        throttle = not query  # only self-limit the automated empty-query sweep
        if throttle and self._throttled():
            return []
        q = (query or self.DEFAULT_QUERY).strip()
        params = {"query": q, "num_pages": str(self.NUM_PAGES),
                  "country": "us", "date_posted": self.DATE_POSTED}
        url = self.BASE + "?" + urllib.parse.urlencode(params)
        headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": self.HOST}
        try:
            data = _http_get_json_auth(url, headers, timeout=25)
        except Exception:
            return []
        if throttle:
            self._mark_called()  # only count automated calls against the cap
        # /search-v2 nests the list under data.jobs; older /search returned a
        # flat list under data. Handle both so the parser is version-proof.
        payload = data.get("data") if isinstance(data, dict) else None
        if isinstance(payload, dict):
            items = payload.get("jobs") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        jobs = []
        for d in items:
            if not isinstance(d, dict):
                continue
            loc = ", ".join([x for x in (d.get("job_city") or "",
                                         d.get("job_state") or "",
                                         d.get("job_country") or "") if x])
            pub = d.get("job_publisher") or ""
            jobs.append(Job(
                source="jsearch",
                company=(d.get("employer_name") or "Unknown").strip(),
                title=(d.get("job_title") or "").strip(),
                url=(d.get("job_apply_link") or d.get("job_google_link") or ""),
                location=loc or ("Remote" if d.get("job_is_remote") else ""),
                remote=bool(d.get("job_is_remote")),
                description=(d.get("job_description") or "")[:2000],
                tags=(["via " + pub] if pub else []),
                posted_ts=str(d.get("job_posted_at_datetime_utc", "") or ""),
                ext_id=str(d.get("job_id", "")),
            ))
        # No client-side substring filter here: JSearch already matches the query
        # server-side (and the query often carries a location like "in Columbus, OH"
        # that never appears verbatim in a posting). Downstream fit/relevance gates
        # still apply in the pipeline.
        return jobs[:limit]


class USAJobsSource(JobSource):
    """USAJOBS — the official US federal government jobs API (data.usajobs.gov).

    Free API key from https://developer.usajobs.gov/apirequest . Provide it via env
    USAJOBS_API_KEY (+ USAJOBS_EMAIL, used as the required User-Agent) or in
    credentials.json -> job_sources.usajobs.{api_key,email}. With no key it returns
    [] so the `us` aggregate keeps working until a key is dropped in.
    """
    name = "usajobs"
    attribution = ("Jobs via the USAJOBS API (data.usajobs.gov), the official US "
                   "federal government job board. Each result links to its usajobs.gov posting.")
    BASE = "https://data.usajobs.gov/api/search"
    DEFAULT_QUERY = "information technology support"

    def fetch(self, query="", limit=25):
        key, email = _usajobs_creds()
        if not key:
            return []
        q = (query or self.DEFAULT_QUERY).strip()
        params = {"Keyword": q, "ResultsPerPage": str(min(max(limit, 1), 500))}
        url = self.BASE + "?" + urllib.parse.urlencode(params)
        headers = {"Authorization-Key": key, "Host": "data.usajobs.gov",
                   "User-Agent": email or USER_AGENT}
        try:
            data = _http_get_json_auth(url, headers)
        except Exception:
            return []
        items = (((data or {}).get("SearchResult") or {}).get("SearchResultItems")) or []
        jobs = []
        for it in items:
            d = (it or {}).get("MatchedObjectDescriptor") or {}
            title = (d.get("PositionTitle") or "").strip()
            if not title:
                continue
            rem = (d.get("PositionRemuneration") or [{}])
            rem = rem[0] if rem else {}
            salary = ""
            try:
                lo, hi = rem.get("MinimumRange"), rem.get("MaximumRange")
                unit = (rem.get("RateIntervalCode") or rem.get("Description") or "").strip()
                if lo and hi:
                    salary = ("$%s - $%s %s" % (format(int(float(lo)), ","),
                                                format(int(float(hi)), ","), unit)).strip()
            except (TypeError, ValueError):
                salary = ""
            details = (d.get("UserArea") or {}).get("Details") or {}
            remote = str(details.get("RemoteIndicator")
                         or details.get("TeleworkEligible") or "").lower() in ("true", "1", "yes")
            jobs.append(Job(
                source="usajobs",
                company=(d.get("OrganizationName") or d.get("DepartmentName")
                         or "U.S. Government").strip(),
                title=title,
                url=d.get("PositionURI") or "",
                location=(d.get("PositionLocationDisplay") or "United States").strip(),
                remote=remote,
                description=(d.get("QualificationSummary") or "")[:2000],
                tags=[c.get("Name") for c in (d.get("JobCategory") or [])
                      if isinstance(c, dict) and c.get("Name")][:6],
                posted_ts=str(d.get("PublicationStartDate") or d.get("PositionStartDate") or ""),
                ext_id=str(d.get("PositionID") or it.get("MatchedObjectId") or ""),
                salary=salary,
                salary_basis="listed" if salary else "",
            ))
        # USAJOBS matches Keyword server-side, so no client-side substring re-filter.
        return jobs[:limit]


class CareerOneStopSource(JobSource):
    """CareerOneStop — US Dept. of Labor job-postings API (api.careeronestop.org).

    Free credentials (API token + userId) from
    https://www.careeronestop.org/Developers/WebAPI/registration.aspx . Provide via
    env CAREERONESTOP_TOKEN + CAREERONESTOP_USERID or in credentials.json ->
    job_sources.careeronestop.{token,user_id}. With no creds it returns [] so the
    `us` aggregate keeps working until they're dropped in.
    """
    name = "careeronestop"
    attribution = ("Jobs via the CareerOneStop Job Search API (api.careeronestop.org), "
                   "sponsored by the U.S. Department of Labor (sourced from the National "
                   "Labor Exchange). Each result links to its original posting.")
    BASE = "https://api.careeronestop.org/v1/jobsearch"
    DEFAULT_QUERY = "information technology support"

    def fetch(self, query="", limit=25):
        token, uid = _careeronestop_creds()
        if not (token and uid):
            return []
        q = (query or self.DEFAULT_QUERY).strip()
        # Positional path: /{userId}/{keyword}/{location}/{radius}/{sort}/{dir}/{start}/{size}/{days}
        path = "/".join([
            urllib.parse.quote(uid, safe=""),
            urllib.parse.quote(q, safe=""),
            "US", "0", "accquisitiondate", "0", "0",
            str(min(max(limit, 1), 100)), "30",
        ])
        url = "%s/%s?source=NLx" % (self.BASE, path)
        try:
            data = _http_get_json_auth(url, {"Authorization": "Bearer " + token})
        except Exception:
            return []
        items = (data or {}).get("Jobs") or []
        jobs = []
        for d in items:
            if not isinstance(d, dict):
                continue
            title = (d.get("JobTitle") or "").strip()
            if not title:
                continue
            loc = (d.get("Location") or "United States").strip()
            jobs.append(Job(
                source="careeronestop",
                company=(d.get("Company") or "Unknown").strip(),
                title=title,
                url=(d.get("URL") or d.get("DetailUrl") or "").strip(),
                location=loc,
                remote="remote" in loc.lower(),
                description="",
                tags=[],
                posted_ts=str(d.get("AccquisitionDate") or d.get("PostDate") or ""),
                ext_id=str(d.get("JvId") or d.get("JobID") or ""),
            ))
        return jobs[:limit]


# --------------------------------------------------------------------------
# Company registry: check each employer's career page DIRECTLY via its ATS
# public API. No key, no scraping, ToS-clean, refreshes daily. A company name
# is NOT guessable to an endpoint (blind slug-guess resolved only ~32%, all of
# them tech), so we keep a curated name->{backend, id} map and a resolver.
# --------------------------------------------------------------------------

def _registry_path():
    """companies.json: <MARCEDDY_HOME>/companies.json overrides the shipped seed."""
    home = _marceddy_home() / "companies.json"
    if home.exists():
        return home
    return Path(__file__).with_name("data") / "companies.json"


def load_company_registry():
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
    except Exception:
        return []
    return [c for c in data.get("companies", []) if isinstance(c, dict)]


def _pull_greenhouse(c):
    slug = c["slug"]
    data = _http_get_json("https://boards-api.greenhouse.io/v1/boards/%s/jobs" % slug, timeout=12)
    out = []
    for d in data.get("jobs", []):
        loc = (d.get("location") or {}).get("name", "")
        out.append(Job(source="company", company=c["name"], title=(d.get("title") or "").strip(),
                       url=d.get("absolute_url", ""), location=loc,
                       remote=("remote" in loc.lower()),
                       posted_ts=str(d.get("updated_at", "")),
                       ext_id="gh-%s-%s" % (slug, d.get("id", ""))))
    return out


def _pull_lever(c):
    slug = c["slug"]
    data = _http_get_json("https://api.lever.co/v0/postings/%s?mode=json" % slug, timeout=12)
    out = []
    for d in (data if isinstance(data, list) else []):
        cat = d.get("categories") or {}
        loc = cat.get("location", "") or ""
        out.append(Job(source="company", company=c["name"], title=(d.get("text") or "").strip(),
                       url=d.get("hostedUrl", ""), location=loc,
                       remote=("remote" in loc.lower()),
                       posted_ts=str(d.get("createdAt", "")),
                       ext_id="lv-%s-%s" % (slug, d.get("id", ""))))
    return out


def _pull_ashby(c):
    slug = c["slug"]
    data = _http_get_json("https://api.ashbyhq.com/posting-api/job-board/%s" % slug, timeout=12)
    out = []
    for d in data.get("jobs", []):
        loc = d.get("location", "") or ""
        out.append(Job(source="company", company=c["name"], title=(d.get("title") or "").strip(),
                       url=d.get("jobUrl", "") or d.get("applyUrl", ""), location=loc,
                       remote=bool(d.get("isRemote")) or ("remote" in loc.lower()),
                       posted_ts=str(d.get("publishedAt", "")),
                       ext_id="ah-%s-%s" % (slug, d.get("id", ""))))
    return out


def _pull_smartrecruiters(c):
    slug = c["slug"]
    data = _http_get_json("https://api.smartrecruiters.com/v1/companies/%s/postings" % slug, timeout=12)
    out = []
    for d in data.get("content", []):
        loc = d.get("location") or {}
        loc_str = ", ".join(x for x in [loc.get("city", ""), loc.get("region", ""), loc.get("country", "").upper()] if x)
        out.append(Job(source="company", company=c["name"], title=(d.get("name") or "").strip(),
                       url="https://jobs.smartrecruiters.com/%s/%s" % (slug, d.get("id", "")),
                       location=loc_str, remote=bool(loc.get("remote")),
                       posted_ts=str(d.get("releasedDate", "")),
                       ext_id="sr-%s-%s" % (slug, d.get("id", ""))))
    return out


def _pull_workable(c):
    slug = c["slug"]
    data = _http_get_json(
        "https://apply.workable.com/api/v1/widget/accounts/%s?details=true" % slug, timeout=12)
    out = []
    for d in data.get("jobs", []):
        loc = ", ".join(x for x in [d.get("city", ""), d.get("state", ""), d.get("country", "")] if x)
        out.append(Job(source="company", company=c["name"], title=(d.get("title") or "").strip(),
                       url=d.get("url", "") or d.get("shortlink", ""), location=loc,
                       remote=bool(d.get("remote")) or ("remote" in loc.lower()),
                       posted_ts=str(d.get("published_on", "")),
                       ext_id="wk-%s-%s" % (slug, d.get("shortcode", ""))))
    return out


def _pull_workday(c, query=""):
    tenant, dc, site = c["tenant"], c["dc"], c["site"]
    # A few tenants have a hostname that differs from the cxs path tenant (e.g.
    # the host uses a hyphen but the API path an underscore, and the underscore
    # host fails TLS cert validation). `host` overrides just the hostname.
    host = c.get("host", tenant)
    url = "https://%s.%s.myworkdayjobs.com/wday/cxs/%s/%s/jobs" % (host, dc, tenant, site)
    data = _http_post_json(url, {"appliedFacets": {}, "limit": 20, "offset": 0,
                                 "searchText": query or ""}, timeout=18)
    base = "https://%s.%s.myworkdayjobs.com/%s" % (host, dc, site)
    out = []
    for d in data.get("jobPostings", []):
        loc = d.get("locationsText", "") or ""
        path = d.get("externalPath", "") or ""
        out.append(Job(source="company", company=c["name"], title=(d.get("title") or "").strip(),
                       url=base + path, location=loc,
                       remote=("remote" in loc.lower()),
                       posted_ts=str(d.get("postedOn", "")),
                       ext_id="wd-%s-%s" % (tenant, d.get("bulletFields", [""])[0] if d.get("bulletFields") else path)))
    return out


def _pull_oracle(c, query=""):
    """Oracle Cloud HCM (Fusion) recruiting REST -- the same no-auth JSON endpoint
    the careers page itself calls. Needs the tenant `host` + `site` (CX_n)."""
    host, site = c["host"], c.get("site", "CX_1")
    url = ("https://%s/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
           "?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber=%s,limit=50"
           % (host, site))
    if query:
        url += ",keyword=%s" % urllib.parse.quote(query)
    data = _http_get_json(url, timeout=15)
    items = data.get("items", [])
    reqs = items[0].get("requisitionList", []) if items else []
    out = []
    for d in reqs:
        loc = d.get("PrimaryLocation", "") or ""
        rid = d.get("Id", "")
        out.append(Job(source="company", company=c["name"], title=(d.get("Title") or "").strip(),
                       url="https://%s/hcmUI/CandidateExperience/en/sites/%s/job/%s" % (host, site, rid),
                       location=loc, remote=("remote" in loc.lower()),
                       posted_ts=str(d.get("PostedDate", "")),
                       ext_id="or-%s-%s" % (site, rid)))
    return out


_BACKEND_PULL = {
    "greenhouse": _pull_greenhouse,
    "lever": _pull_lever,
    "ashby": _pull_ashby,
    "smartrecruiters": _pull_smartrecruiters,
    "workable": _pull_workable,
}


def resolve_company(name, slug=None):
    """Try the no-key light ATS backends for a slug and return (backend, slug, n)
    for the first that yields jobs. Workday is NOT auto-resolvable (needs the
    tenant+dc+site triple read off the careers page), so it is never guessed."""
    cand = slug or slugify(name, 40).replace("-", "")
    variants = [cand, slug or name.lower().replace(" ", ""), slugify(name, 40)]
    seen = []
    for s in variants:
        if not s or s in seen:
            continue
        seen.append(s)
        for backend, pull in _BACKEND_PULL.items():
            try:
                jobs = pull({"name": name, "slug": s})
            except Exception:
                continue
            if jobs:
                return backend, s, len(jobs)
    return None, None, 0


class CompanyRegistrySource(JobSource):
    """Check curated employers' career pages directly via their ATS public APIs.

    Reads companies.json (per-home override or the shipped seed). Each entry is
    pulled from its own backend; results join the normal fit->apply->digest path.
    Covers the Columbus enterprises (Workday) that the remote-board aggregators
    miss entirely.
    """
    name = "companies"
    attribution = ("Jobs pulled directly from employers' own career pages via their "
                   "ATS public APIs (Greenhouse/Lever/Ashby/SmartRecruiters/Workable/Workday). "
                   "No scraping; these are the same official endpoints job aggregators use.")

    def __init__(self, registry=None):
        self._registry = registry  # injectable for tests

    def fetch(self, query="", limit=25):
        companies = self._registry if self._registry is not None else load_company_registry()
        out = []
        for c in companies:
            backend = (c.get("backend") or "").lower()
            if backend == "browser":
                continue  # browser entries are slow -> handled by BrowserRegistrySource
            try:
                if backend == "workday":
                    out.extend(_pull_workday(c, query=query))
                elif backend == "oracle":
                    out.extend(_pull_oracle(c, query=query))
                elif backend in _BACKEND_PULL:
                    out.extend(_BACKEND_PULL[backend](c))
            except Exception:
                continue  # one dead board never sinks the sweep
        # These are CURATED US employers, so every posting is relevant -- drop
        # only clearly-foreign offices. (Workday reports a facility/street as the
        # location, which would wrongly fail a require-US-match filter.)
        out = [j for j in out if not _is_foreign(j.location)]
        if query:
            q = query.lower()
            out = [j for j in out if q in j.text_blob()]
        return out[:limit]


class BrowserRegistrySource(JobSource):
    """Harvest the registry's `browser` entries via a headless browser. Separate
    from CompanyRegistrySource (and the hourly `us` sweep) because Chromium per
    site is slow -> meant for a low-cadence cron. Covers ATSs that won't serve a
    clean no-auth JSON board (Taleo, Phenom, SuccessFactors). iCIMS hard-blocks
    datacenter IPs and yields [] here (needs a residential IP / Ed's laptop)."""
    name = "companies-browser"
    attribution = ("Jobs read from employers' rendered career pages via a headless "
                   "browser (their own JS fetches the listings; we only read the DOM).")

    def __init__(self, registry=None):
        self._registry = registry

    def fetch(self, query="", limit=25):
        from .browser_harvest import harvest
        companies = self._registry if self._registry is not None else load_company_registry()
        out = []
        for c in companies:
            if (c.get("backend") or "").lower() != "browser":
                continue
            try:
                out.extend(harvest(c["url"], c["name"]))
            except Exception:
                continue
        out = [j for j in out if not _is_foreign(j.location)]
        if query:
            q = query.lower()
            out = [j for j in out if q in j.text_blob()]
        return out[:limit]


class USCombinedSource(JobSource):
    """Aggregate the legitimate US sources into one --source us."""
    name = "us"
    attribution = ("Aggregated US sources: company career pages (registry: "
                   "Greenhouse/Lever/Ashby/SmartRecruiters/Workable/Workday) + The Muse "
                   "+ Greenhouse boards + Remotive + RemoteOK + Jobicy + SimplyHired "
                   "+ Himalayas + Working Nomads + We Work Remotely + DevITjobs + 4 Day "
                   "Week + JSearch/Google-for-Jobs (adds Indeed & LinkedIn when a RapidAPI "
                   "key is configured).")

    def fetch(self, query="", limit=25):
        out = []
        # IndeedFileSource (live Indeed connection) first, then JSearch, so their
        # Indeed/LinkedIn results survive the dedup+[:limit] truncation (highest-
        # priority coverage per Ed); the free aggregators fill in the remainder.
        for src in (IndeedFileSource(), JSearchSource(), CompanyRegistrySource(),
                    SimplyHiredSource(), MuseSource(), GreenhouseSource(),
                    RemotiveSource(), RemoteOKSource(), JobicySource(),
                    HimalayasSource(), WorkingNomadsSource(), WeWorkRemotelySource(),
                    DevITjobsSource(), FourDayWeekSource(),
                    USAJobsSource(), CareerOneStopSource()):
            try:
                out.extend(src.fetch(query, limit * 3))
            except Exception:
                continue
        out = [j for j in out if _is_us(j.location) or (j.remote and _remote_ok(j.location))]
        seen, uniq = set(), []
        for j in out:
            k = (j.company.lower().strip(), j.title.lower().strip())
            if k in seen:
                continue
            seen.add(k)
            uniq.append(j)
        return uniq[:limit]


_SOURCES = {
    "fixture": FixtureSource,
    "arbeitnow": ArbeitnowSource,
    "remotive": RemotiveSource,
    "muse": MuseSource,
    "greenhouse": GreenhouseSource,
    "remoteok": RemoteOKSource,
    "jobicy": JobicySource,
    "simplyhired": SimplyHiredSource,
    "himalayas": HimalayasSource,
    "workingnomads": WorkingNomadsSource,
    "weworkremotely": WeWorkRemotelySource,
    "devitjobs": DevITjobsSource,
    "fourdayweek": FourDayWeekSource,
    "usajobs": USAJobsSource,
    "careeronestop": CareerOneStopSource,
    "jsearch": JSearchSource,
    "indeed": IndeedFileSource,
    "companies": CompanyRegistrySource,
    "companies-browser": BrowserRegistrySource,
    "us": USCombinedSource,
}


def get_source(name, config=None, fixture_path=None):
    name = (name or "fixture").lower()
    if name == "fixture":
        return FixtureSource(fixture_path)
    cls = _SOURCES.get(name)
    if cls is None:
        raise ValueError("unknown source: %s (choose from %s)" % (name, ", ".join(_SOURCES)))
    return cls()
