import inspect

import marceddy.sources as S
from marceddy.sources import (HimalayasSource, WorkingNomadsSource,
                              WeWorkRemotelySource, USCombinedSource, get_source)


def test_registered_and_in_us_sweep():
    for name in ("himalayas", "workingnomads", "weworkremotely"):
        assert name in S._SOURCES
        assert get_source(name).name == name
    src = inspect.getsource(USCombinedSource.fetch)
    assert "HimalayasSource()" in src
    assert "WorkingNomadsSource()" in src
    assert "WeWorkRemotelySource()" in src


def test_himalayas_parses_fields_and_salary(monkeypatch):
    payload = {"jobs": [{
        "title": "Senior Python Engineer",
        "companyName": "Acme",
        "locationRestrictions": ["United States"],
        "minSalary": 120000, "maxSalary": 160000,
        "currency": "USD", "salaryPeriod": "yearly",
        "categories": ["Engineering"],
        "applicationLink": "https://himalayas.app/companies/acme/jobs/1",
        "guid": "https://himalayas.app/companies/acme/jobs/1",
        "pubDate": 1782582289,
    }]}
    monkeypatch.setattr(S, "_http_get_json", lambda url, timeout=25: payload)
    jobs = HimalayasSource().fetch("", 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "himalayas"
    assert j.company == "Acme"
    assert j.title == "Senior Python Engineer"
    assert j.location == "United States"
    assert j.remote is True
    assert j.salary == "USD 120,000-160,000 yearly"
    assert j.salary_basis == "listed"


def test_workingnomads_parses_list(monkeypatch):
    payload = [{
        "url": "https://www.workingnomads.com/job/go/1/",
        "title": "Remote SRE",
        "company_name": "Globex",
        "location": "North America",
        "tags": "linux,kubernetes,aws",
        "pub_date": "2026-06-25T11:03:18-04:00",
        "description": "<p>Run things</p>",
    }]
    monkeypatch.setattr(S, "_http_get_json", lambda url, timeout=25: payload)
    jobs = WorkingNomadsSource().fetch("", 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "Globex"
    assert j.title == "Remote SRE"
    assert j.location == "North America"
    assert "kubernetes" in j.tags
    assert j.remote is True


WWR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Initech: Backend Engineer</title>
    <region>Anywhere in the World</region>
    <category>Programming</category>
    <link>https://weworkremotely.com/remote-jobs/initech-backend</link>
    <guid>https://weworkremotely.com/remote-jobs/initech-backend</guid>
    <pubDate>Sat, 27 Jun 2026 01:08:59 +0000</pubDate>
  </item>
  <item>
    <title>Initech: Backend Engineer</title>
    <region>Anywhere in the World</region>
    <category>Programming</category>
    <link>https://weworkremotely.com/remote-jobs/initech-backend</link>
    <guid>https://weworkremotely.com/remote-jobs/initech-backend</guid>
    <pubDate>Sat, 27 Jun 2026 01:08:59 +0000</pubDate>
  </item>
  <item>
    <title>Plain Title No Colon</title>
    <region>USA Only</region>
    <link>https://weworkremotely.com/remote-jobs/plain</link>
    <guid>https://weworkremotely.com/remote-jobs/plain</guid>
  </item>
</channel></rss>"""


def test_weworkremotely_splits_title_and_dedupes(monkeypatch):
    monkeypatch.setattr(S, "_http_get_text", lambda url, timeout=25: WWR_RSS)
    jobs = WeWorkRemotelySource().fetch("", 10)
    # 3 items but two are identical -> deduped to 2
    assert len(jobs) == 2
    first = jobs[0]
    assert first.company == "Initech"
    assert first.title == "Backend Engineer"
    assert first.remote is True
    # title with no "Company:" prefix keeps the raw title, company Unknown
    plain = jobs[1]
    assert plain.title == "Plain Title No Colon"
    assert plain.company == "Unknown"


def test_weworkremotely_bad_xml_is_noop(monkeypatch):
    monkeypatch.setattr(S, "_http_get_text", lambda url, timeout=25: "<not xml")
    assert WeWorkRemotelySource().fetch("", 10) == []
