import inspect
import json

from marceddy.sources import SimplyHiredSource, USCombinedSource, get_source
import marceddy.sources as S


def _fixture_html(jobs):
    """Wrap a jobs list the way SimplyHired ships it: a __NEXT_DATA__ script tag
    whose JSON carries props.pageProps.jobs."""
    blob = {"props": {"pageProps": {"jobs": jobs}}}
    return (
        "<html><head></head><body>"
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(blob)
        + "</script></body></html>"
    )


SAMPLE = [
    {
        "jobKey": "abc123",
        "title": "Cyber Operations Lead- Cloud/IaaS",
        "company": "Leidos",
        "location": "Whitehall, OH",
        "botUrl": "/job/abc123",
        "salaryInfo": "$87,100 - $157,450 a year",
        "snippet": "Lead cloud security operations.",
        "jobTypes": ["Full-time"],
        "remoteAttributes": [],
    },
    {
        "jobKey": "def456",
        "title": "Remote Help Desk Technician",
        "company": "EOS",
        "location": "Remote",
        "botUrl": "/job/def456",
        "salaryInfo": "",
        "snippet": "Support end users.",
        "jobTypes": ["Contract"],
        "remoteAttributes": ["remote"],
    },
]


def test_registered_in_sources():
    assert "simplyhired" in S._SOURCES
    assert get_source("simplyhired").name == "simplyhired"


def test_included_in_us_aggregate():
    # The `us` sweep must route through SimplyHired too.
    assert "SimplyHiredSource()" in inspect.getsource(USCombinedSource.fetch)


def test_parse_extracts_fields_and_listed_salary():
    jobs = SimplyHiredSource()._parse(_fixture_html(SAMPLE))
    assert len(jobs) == 2
    j = jobs[0]
    assert j.source == "simplyhired"
    assert j.company == "Leidos"
    assert j.title == "Cyber Operations Lead- Cloud/IaaS"
    assert j.url == "https://www.simplyhired.com/job/abc123"
    assert j.location == "Whitehall, OH"
    assert j.salary == "$87,100 - $157,450 a year"
    assert j.salary_basis == "listed"
    assert j.ext_id == "abc123"
    assert j.job_id.startswith("simplyhired-")


def test_parse_marks_remote_and_blank_salary():
    jobs = SimplyHiredSource()._parse(_fixture_html(SAMPLE))
    remote = jobs[1]
    assert remote.remote is True
    assert remote.salary == ""
    assert remote.salary_basis == ""


def test_parse_bad_or_empty_html_is_clean_noop():
    assert SimplyHiredSource()._parse("") == []
    assert SimplyHiredSource()._parse("<html>no next data here</html>") == []
    # malformed JSON inside the tag must not raise
    bad = ('<script id="__NEXT_DATA__" type="application/json">{not json}</script>')
    assert SimplyHiredSource()._parse(bad) == []
