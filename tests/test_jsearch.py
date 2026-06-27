"""JSearch (Indeed/LinkedIn via Google-for-Jobs) source tests — no network."""
import marceddy.sources as S
from marceddy.sources import JSearchSource, USCombinedSource, get_source


def test_jsearch_registered():
    assert get_source("jsearch").name == "jsearch"
    assert "jsearch" in S._SOURCES


def test_no_key_is_clean_noop(monkeypatch, tmp_path):
    # No env key and an empty home -> returns [] instead of erroring.
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    assert JSearchSource().fetch("help desk", 10) == []


def test_key_from_credentials_then_parses(monkeypatch, tmp_path):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    (tmp_path / "credentials.json").write_text(
        '{"job_sources": {"jsearch": {"api_key": "TESTKEY"}}}')
    assert S._jsearch_key() == "TESTKEY"

    captured = {}

    def fake_get(url, headers, timeout=25):
        captured["url"] = url
        captured["headers"] = headers
        # /search-v2 nests the job list under data.jobs (real response shape).
        return {"status": "OK", "data": {"jobs": [{
            "job_id": "abc123",
            "job_title": "IT Help Desk Technician",
            "employer_name": "Acme Corp",
            "job_apply_link": "https://www.indeed.com/viewjob?jk=abc123",
            "job_city": "Columbus", "job_state": "OH", "job_country": "US",
            "job_is_remote": False,
            "job_publisher": "Indeed",
            "job_description": "Provide tier 1 desktop support.",
            "job_posted_at_datetime_utc": "2026-06-25T00:00:00.000Z",
        }], "cursor": "xyz"}}

    monkeypatch.setattr(S, "_http_get_json_auth", fake_get)
    # A location-bearing query must NOT be re-filtered client-side: JSearch
    # already matched server-side, and "in Columbus, OH" appears in no posting
    # verbatim. (Regression guard for the bug that silently returned 0.)
    jobs = JSearchSource().fetch("help desk in Columbus, OH", 10)
    assert captured["headers"]["X-RapidAPI-Key"] == "TESTKEY"
    assert "search-v2" in captured["url"]
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "jsearch"
    assert j.title == "IT Help Desk Technician"
    assert j.company == "Acme Corp"
    assert j.url == "https://www.indeed.com/viewjob?jk=abc123"
    assert j.location == "Columbus, OH, US"
    assert "via Indeed" in j.tags
    assert j.job_id.startswith("jsearch-")


def test_us_aggregate_includes_jsearch():
    # The hourly `us` sweep must now route through JSearch too.
    import inspect
    assert "JSearchSource()" in inspect.getsource(USCombinedSource.fetch)


def test_is_us_recognizes_full_state_names_and_country():
    # JSearch returns "City, <Full State Name>, US" — must read as US.
    assert S._is_us("Alexandria, Virginia, US")
    assert S._is_us("Washington, District of Columbia, US")
    assert S._is_us("Columbus, OH")
    assert not S._is_us("Toronto, Ontario, Canada")
    assert not S._is_us("")


def _creds_with_key(tmp_path):
    (tmp_path / "credentials.json").write_text(
        '{"job_sources": {"jsearch": {"api_key": "K"}}}')


def _one_job(*_a, **_k):
    return {"status": "OK", "data": {"jobs": [{
        "job_id": "1", "job_title": "Help Desk", "employer_name": "X",
        "job_apply_link": "u", "job_city": "Columbus",
        "job_state": "OH", "job_country": "US"}]}}


def test_throttle_limits_automated_sweep(monkeypatch, tmp_path):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    monkeypatch.delenv("MARCEDDY_JSEARCH_INTERVAL_MIN", raising=False)
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    _creds_with_key(tmp_path)
    calls = {"n": 0}

    def fake_get(url, headers, timeout=25):
        calls["n"] += 1
        return _one_job()

    monkeypatch.setattr(S, "_http_get_json_auth", fake_get)
    src = JSearchSource()
    assert len(src.fetch("", 10)) == 1          # 1st automated call -> hits API
    assert src.fetch("", 10) == []              # within window -> throttled, no hit
    assert calls["n"] == 1
    assert len(src.fetch("help desk", 10)) == 1  # manual query never throttled
    assert calls["n"] == 2


def test_throttle_disabled_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    monkeypatch.setenv("MARCEDDY_JSEARCH_INTERVAL_MIN", "0")
    _creds_with_key(tmp_path)
    calls = {"n": 0}

    def fake_get(url, headers, timeout=25):
        calls["n"] += 1
        return {"status": "OK", "data": {"jobs": []}}

    monkeypatch.setattr(S, "_http_get_json_auth", fake_get)
    src = JSearchSource()
    src.fetch("", 5)
    src.fetch("", 5)
    assert calls["n"] == 2  # interval=0 -> no throttle
