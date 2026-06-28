import inspect

import marceddy.sources as S
from marceddy.sources import (USAJobsSource, CareerOneStopSource,
                              USCombinedSource, get_source)


def test_registered_and_in_us_sweep():
    for name in ("usajobs", "careeronestop"):
        assert name in S._SOURCES
        assert get_source(name).name == name
    src = inspect.getsource(USCombinedSource.fetch)
    assert "USAJobsSource()" in src
    assert "CareerOneStopSource()" in src


def test_usajobs_noop_without_key(monkeypatch):
    monkeypatch.setattr(S, "_usajobs_creds", lambda: ("", ""))
    assert USAJobsSource().fetch("it", 5) == []


def test_careeronestop_noop_without_creds(monkeypatch):
    monkeypatch.setattr(S, "_careeronestop_creds", lambda: ("", ""))
    assert CareerOneStopSource().fetch("it", 5) == []


USAJOBS_FIXTURE = {
    "SearchResult": {
        "SearchResultItems": [
            {
                "MatchedObjectId": "123",
                "MatchedObjectDescriptor": {
                    "PositionID": "VA-123",
                    "PositionTitle": "IT Specialist (Customer Support)",
                    "OrganizationName": "Department of Veterans Affairs",
                    "PositionURI": "https://www.usajobs.gov/job/123",
                    "PositionLocationDisplay": "Washington, District of Columbia",
                    "PositionRemuneration": [
                        {"MinimumRange": "60000.0", "MaximumRange": "90000.0",
                         "RateIntervalCode": "Per Year"}],
                    "QualificationSummary": "Provide IT customer support.",
                    "JobCategory": [{"Name": "Information Technology Management"}],
                    "PublicationStartDate": "2026-06-25",
                    "UserArea": {"Details": {"RemoteIndicator": True}},
                },
            }
        ]
    }
}


def test_usajobs_parses_federal_job(monkeypatch):
    monkeypatch.setattr(S, "_usajobs_creds", lambda: ("KEY", "me@example.com"))
    monkeypatch.setattr(S, "_http_get_json_auth", lambda url, headers, timeout=25: USAJOBS_FIXTURE)
    jobs = USAJobsSource().fetch("it support", 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "usajobs"
    assert j.company == "Department of Veterans Affairs"
    assert j.title == "IT Specialist (Customer Support)"
    assert j.url == "https://www.usajobs.gov/job/123"
    assert j.location == "Washington, District of Columbia"
    assert j.remote is True
    assert j.salary == "$60,000 - $90,000 Per Year"
    assert j.salary_basis == "listed"
    assert j.ext_id == "VA-123"


CAREERONESTOP_FIXTURE = {
    "Jobs": [
        {
            "JvId": "xyz789",
            "JobTitle": "Help Desk Technician",
            "Company": "Acme Federal Services",
            "Location": "Columbus, OH",
            "URL": "https://www.careeronestop.org/job/xyz789",
            "AccquisitionDate": "06/25/2026",
        }
    ],
    "RecordCount": 1,
}


def test_careeronestop_parses_job(monkeypatch):
    monkeypatch.setattr(S, "_careeronestop_creds", lambda: ("TOKEN", "USERID"))
    monkeypatch.setattr(S, "_http_get_json_auth", lambda url, headers, timeout=25: CAREERONESTOP_FIXTURE)
    jobs = CareerOneStopSource().fetch("help desk", 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "careeronestop"
    assert j.company == "Acme Federal Services"
    assert j.title == "Help Desk Technician"
    assert j.url == "https://www.careeronestop.org/job/xyz789"
    assert j.location == "Columbus, OH"
    assert j.ext_id == "xyz789"


def test_keyed_sources_handle_bad_payload(monkeypatch):
    monkeypatch.setattr(S, "_usajobs_creds", lambda: ("KEY", "me@example.com"))
    monkeypatch.setattr(S, "_careeronestop_creds", lambda: ("TOKEN", "USERID"))
    monkeypatch.setattr(S, "_http_get_json_auth", lambda url, headers, timeout=25: {})
    assert USAJobsSource().fetch("it", 5) == []
    assert CareerOneStopSource().fetch("it", 5) == []
