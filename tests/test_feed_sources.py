import inspect

import marceddy.sources as S
from marceddy.sources import (DevITjobsSource, FourDayWeekSource,
                              USCombinedSource, get_source)


def test_registered_and_in_us_sweep():
    for name in ("devitjobs", "fourdayweek"):
        assert name in S._SOURCES
        assert get_source(name).name == name
    src = inspect.getsource(USCombinedSource.fetch)
    assert "DevITjobsSource()" in src
    assert "FourDayWeekSource()" in src


def test_devitjobs_parses_us_job_and_salary(monkeypatch):
    payload = [{
        "_id": "abc123",
        "name": "Senior Backend Engineer",
        "company": "UseBlocky",
        "jobUrl": "UseBlocky-Senior-Backend-Engineer",
        "actualCity": "New-York-City",
        "stateCategory": "New-York",
        "workplace": "remote",
        "remoteType": "anywhere",
        "annualSalaryFrom": 200000,
        "annualSalaryTo": 260000,
        "technologies": ["python", "go", "aws"],
        "activeFrom": "2026-06-25T12:02:58.891+02:00",
    }]
    monkeypatch.setattr(S, "_http_get_json", lambda url, timeout=25: payload)
    jobs = DevITjobsSource().fetch("", 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "devitjobs"
    assert j.company == "UseBlocky"
    assert j.title == "Senior Backend Engineer"
    assert j.url == "https://devitjobs.us/job/UseBlocky-Senior-Backend-Engineer"
    assert j.location == "New York City, New York"
    assert j.remote is True
    assert j.salary == "$200,000-$260,000 a year"
    assert j.salary_basis == "listed"
    assert "python" in j.tags


def test_fourdayweek_parses_jobs_envelope(monkeypatch):
    payload = {"jobs": [{
        "id": "xyz",
        "title": "Support Engineer",
        "company_name": "ImprovMX",
        "slug": "support-engineer-at-improvmx-123",
        "work_arrangement": "remote",
        "locations": [{"city": "", "country": "United States"}],
        "category": "engineering",
        "level": "mid",
        "posted": 1782443697,
    }], "total": 1, "page": 1, "has_more": False}
    monkeypatch.setattr(S, "_http_get_json", lambda url, timeout=25: payload)
    jobs = FourDayWeekSource().fetch("", 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "fourdayweek"
    assert j.company == "ImprovMX"
    assert j.title == "Support Engineer"
    assert j.url == "https://4dayweek.io/jobs/support-engineer-at-improvmx-123"
    assert j.location == "United States"
    assert j.remote is True
    assert "4-day week" in j.tags


def test_feeds_handle_garbage(monkeypatch):
    monkeypatch.setattr(S, "_http_get_json", lambda url, timeout=25: {})
    assert DevITjobsSource().fetch("", 5) == []
    assert FourDayWeekSource().fetch("", 5) == []
