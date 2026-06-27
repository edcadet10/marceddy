"""Company-registry source: check employers' career pages directly via their
ATS public APIs (Greenhouse/Lever/Ashby/SmartRecruiters/Workable/Workday).
All offline -- HTTP layer is monkeypatched."""
import marceddy.sources as S
from marceddy.sources import (CompanyRegistrySource, USCombinedSource,
                              get_source, resolve_company, load_company_registry)


def test_registered_and_seed_loads():
    assert get_source("companies").name == "companies"
    assert "companies" in S._SOURCES
    reg = load_company_registry()           # shipped seed must be readable + non-empty
    assert len(reg) >= 5
    assert all("backend" in c and "name" in c for c in reg)


def test_us_aggregate_includes_registry():
    import inspect
    assert "CompanyRegistrySource()" in inspect.getsource(USCombinedSource.fetch)


def test_greenhouse_backend_parse(monkeypatch):
    def fake_get(url, timeout=25):
        assert "boards-api.greenhouse.io/v1/boards/acme/jobs" in url
        return {"jobs": [{"title": "IT Support Specialist", "absolute_url": "https://acme/jobs/1",
                          "location": {"name": "Columbus, OH"}, "id": 1, "updated_at": "2026-06-26"}]}
    monkeypatch.setattr(S, "_http_get_json", fake_get)
    jobs = CompanyRegistrySource(registry=[{"name": "Acme", "backend": "greenhouse", "slug": "acme"}]).fetch()
    assert len(jobs) == 1
    assert jobs[0].company == "Acme" and jobs[0].source == "company"
    assert jobs[0].title == "IT Support Specialist"
    assert jobs[0].ext_id.startswith("gh-acme-")


def test_workday_backend_post_and_keeps_facility_location(monkeypatch):
    """Workday reports a facility/street as the location -- it must NOT be dropped
    by a require-US filter (it isn't a foreign office)."""
    seen = {}

    def fake_post(url, payload, timeout=20):
        seen["url"] = url
        seen["payload"] = payload
        return {"jobPostings": [{
            "title": "IT Service Desk Agent",
            "externalPath": "/job/GRANT-MEDICAL-CENTER/IT-Service-Desk_JR1",
            "locationsText": "GRANT MEDICAL CENTER",   # facility name, not "City, ST"
            "postedOn": "Posted Today", "bulletFields": ["JR1"]}]}
    monkeypatch.setattr(S, "_http_post_json", fake_post)
    c = {"name": "OhioHealth", "backend": "workday", "tenant": "ohiohealth",
         "dc": "wd5", "site": "OhioHealthJobs"}
    jobs = CompanyRegistrySource(registry=[c]).fetch()
    assert "ohiohealth.wd5.myworkdayjobs.com/wday/cxs/ohiohealth/OhioHealthJobs/jobs" in seen["url"]
    assert "searchText" in seen["payload"]
    assert len(jobs) == 1                       # kept despite non-US-looking location
    assert jobs[0].title == "IT Service Desk Agent"
    assert jobs[0].url.endswith("/job/GRANT-MEDICAL-CENTER/IT-Service-Desk_JR1")


def test_workday_host_override(monkeypatch):
    """Some tenants have host != cxs-path tenant (hyphen host, underscore path);
    the underscore host even fails TLS. `host` overrides only the hostname."""
    seen = {}

    def fake_post(url, payload, timeout=20):
        seen["url"] = url
        return {"jobPostings": [{"title": "Packaging Tech", "externalPath": "/job/x",
                                 "locationsText": "New Albany, OH", "postedOn": "Today"}]}
    monkeypatch.setattr(S, "_http_post_json", fake_post)
    c = {"name": "Pharmavite", "backend": "workday", "tenant": "vhr_otsuka",
         "host": "vhr-otsuka", "dc": "wd1", "site": "Pharmavite"}
    jobs = CompanyRegistrySource(registry=[c]).fetch()
    # host segment uses the hyphen form; cxs path uses the underscore tenant
    assert "https://vhr-otsuka.wd1.myworkdayjobs.com/wday/cxs/vhr_otsuka/Pharmavite/jobs" == seen["url"]
    assert len(jobs) == 1 and jobs[0].url.startswith("https://vhr-otsuka.wd1.myworkdayjobs.com/Pharmavite")


def test_oracle_hcm_backend(monkeypatch):
    """Oracle Cloud HCM recruiting REST -- no-auth JSON the careers page calls."""
    def fake_get(url, timeout=25):
        assert "recruitingCEJobRequisitions" in url and "siteNumber=CX_1" in url
        return {"items": [{"requisitionList": [
            {"Id": "R1", "Title": "IT Analyst",
             "PrimaryLocation": "Columbus, OH, United States", "PostedDate": "2026-06-27"}]}]}
    monkeypatch.setattr(S, "_http_get_json", fake_get)
    c = {"name": "Worthington", "backend": "oracle",
         "host": "fa-eygo-saasfaprod1.fa.ocs.oraclecloud.com", "site": "CX_1"}
    jobs = CompanyRegistrySource(registry=[c]).fetch()
    assert len(jobs) == 1 and jobs[0].title == "IT Analyst"
    assert jobs[0].ext_id == "or-CX_1-R1"


def test_foreign_office_dropped(monkeypatch):
    def fake_get(url, timeout=25):
        return {"jobs": [
            {"title": "Support US", "absolute_url": "u1", "location": {"name": "Austin, TX"}, "id": 1},
            {"title": "Support DE", "absolute_url": "u2", "location": {"name": "Berlin, Germany"}, "id": 2}]}
    monkeypatch.setattr(S, "_http_get_json", fake_get)
    jobs = CompanyRegistrySource(registry=[{"name": "X", "backend": "greenhouse", "slug": "x"}]).fetch()
    titles = {j.title for j in jobs}
    assert "Support US" in titles and "Support DE" not in titles


def test_one_dead_board_does_not_sink_sweep(monkeypatch):
    def fake_get(url, timeout=25):
        if "dead" in url:
            raise OSError("404")
        return {"jobs": [{"title": "Live Role", "absolute_url": "u", "location": {"name": "OH"}, "id": 9}]}
    monkeypatch.setattr(S, "_http_get_json", fake_get)
    reg = [{"name": "Dead", "backend": "greenhouse", "slug": "dead"},
           {"name": "Live", "backend": "greenhouse", "slug": "live"}]
    jobs = CompanyRegistrySource(registry=reg).fetch()
    assert [j.company for j in jobs] == ["Live"]


def test_resolver_finds_first_backend_with_jobs(monkeypatch):
    # greenhouse empty, ashby has jobs -> resolver returns ashby.
    def fake_get(url, timeout=25):
        if "greenhouse" in url:
            return {"jobs": []}
        if "ashbyhq" in url:
            return {"jobs": [{"title": "T", "jobUrl": "u", "location": "Remote", "id": "a1"}]}
        raise OSError("nope")
    monkeypatch.setattr(S, "_http_get_json", fake_get)
    backend, slug, n = resolve_company("Some Co", slug="someco")
    assert backend == "ashby" and slug == "someco" and n == 1


def test_resolver_unresolved_returns_none(monkeypatch):
    monkeypatch.setattr(S, "_http_get_json", lambda *a, **k: {"jobs": []})
    backend, slug, n = resolve_company("Nobody", slug="nobody")
    assert backend is None and n == 0


def test_browser_entries_skipped_by_json_source():
    """`browser` entries must NOT run in the hourly JSON sweep (too slow)."""
    reg = [{"name": "Slow", "backend": "browser", "url": "https://x/jobs"}]
    assert CompanyRegistrySource(registry=reg).fetch() == []


def test_browser_source_harvests(monkeypatch):
    import marceddy.sources as SS
    from marceddy.models import Job
    def fake_harvest(url, company, **k):
        assert url == "https://x/jobs"
        return [Job(source="company", company=company, title="IT Manager 1", url="u", location="Columbus, OH")]
    import marceddy.browser_harvest as BH
    monkeypatch.setattr(BH, "harvest", fake_harvest)
    reg = [{"name": "State of Ohio", "backend": "browser", "url": "https://x/jobs"},
           {"name": "Skip", "backend": "greenhouse", "slug": "z"}]
    jobs = SS.BrowserRegistrySource(registry=reg).fetch()
    assert len(jobs) == 1 and jobs[0].title == "IT Manager 1"


def test_home_registry_overrides_seed(monkeypatch, tmp_path):
    (tmp_path / "companies.json").write_text('{"companies": [{"name": "Only", "backend": "lever", "slug": "only"}]}')
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    reg = load_company_registry()
    assert reg == [{"name": "Only", "backend": "lever", "slug": "only"}]
