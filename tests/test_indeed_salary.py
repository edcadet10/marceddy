"""Direct-Indeed source + salary-in-digest + salary research merge — no network."""
import argparse
import json
import os
import time

import marceddy.sources as S
from marceddy.sources import IndeedFileSource, USCombinedSource, get_source
from marceddy.digest import _salary_line, build_digest
from marceddy.ledger import Ledger
from marceddy.cli import cmd_salary_apply, cmd_salary_missing


def test_indeed_registered_and_first_in_us():
    assert get_source("indeed").name == "indeed"
    import inspect
    src = inspect.getsource(USCombinedSource.fetch)
    assert "IndeedFileSource()" in src
    # must be iterated before the free aggregators so its results survive [:limit]
    assert src.index("IndeedFileSource()") < src.index("MuseSource()")


def test_indeed_file_source_reads_salary(monkeypatch, tmp_path):
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    (tmp_path / "indeed_inbox.json").write_text(json.dumps([
        {"company": "Acme", "title": "Help Desk Technician",
         "url": "https://to.indeed.com/x", "location": "Columbus, OH",
         "remote": False, "salary": "$45,000 a year", "posted": "2d", "ext_id": "jk1"},
        {"company": "Beta", "title": "Desktop Support",
         "url": "https://to.indeed.com/y", "location": "Remote",
         "remote": True, "salary": "", "posted": "", "ext_id": "jk2"},
        {"bad": "row"},  # skipped: no title/url
    ]))
    jobs = IndeedFileSource().fetch("", 10)
    assert len(jobs) == 2
    a = next(j for j in jobs if j.company == "Acme")
    assert a.source == "indeed" and a.salary == "$45,000 a year"
    assert a.salary_estimated is False and a.salary_basis
    b = next(j for j in jobs if j.company == "Beta")
    assert b.remote is True and b.salary == ""


def test_indeed_file_stale_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    p = tmp_path / "indeed_inbox.json"
    p.write_text('[{"company":"X","title":"Help Desk","url":"u"}]')
    old = time.time() - (IndeedFileSource.MAX_AGE_MIN + 30) * 60
    os.utime(p, (old, old))
    assert IndeedFileSource().fetch("", 10) == []


def test_indeed_file_missing_or_garbled(monkeypatch, tmp_path):
    monkeypatch.setenv("MARCEDDY_HOME", str(tmp_path))
    assert IndeedFileSource().fetch("", 10) == []          # no file
    (tmp_path / "indeed_inbox.json").write_text("{ not json")
    assert IndeedFileSource().fetch("", 10) == []          # garbled


def test_location_line_render():
    from marceddy.digest import _location_line
    assert _location_line({"remote": True, "location": ""}) == "Remote"
    assert _location_line({"remote": True, "location": "Austin, TX"}) == "Remote (Austin, TX)"
    assert _location_line({"remote": False, "location": "Columbus, OH"}) == "Columbus, OH"
    assert _location_line({"remote": False, "location": ""}) == "see posting"


def test_digest_shows_location_per_job(cfg):
    led = Ledger.load(cfg)
    led.upsert({"job_id": "1", "status": "ready_to_submit", "company": "Acme",
                "title": "Help Desk", "url": "u", "fit_score": 0.9,
                "ready_ts": "2026-06-25T00:00:00Z", "location": "Dublin, OH",
                "remote": False})
    led.save()
    assert "location: Dublin, OH" in build_digest(led)


def test_hourly_pay_parsing():
    from marceddy.digest import hourly_pay
    assert hourly_pay("$20 - $23 an hour") == 23.0
    assert round(hourly_pay("$60,000 a year"), 1) == 28.8     # below $30/hr
    assert round(hourly_pay("$85,000 - $100,000 a year")) == 48
    assert hourly_pay("$35 an hour") == 35.0
    assert hourly_pay("") is None and hourly_pay("N/A") is None


def test_qualifies_fit_and_pay():
    from marceddy.digest import _qualifies
    hi = {"fit_score": 0.7, "salary": "$40 an hour"}
    assert _qualifies(hi, 0.6, 30) is True
    assert _qualifies({"fit_score": 0.51, "salary": "$40 an hour"}, 0.6, 30) is False  # fit too low
    assert _qualifies({"fit_score": 0.7, "salary": "$22 an hour"}, 0.6, 30) is False   # pay too low
    assert _qualifies({"fit_score": 0.7, "salary": ""}, 0.6, 30) is False              # unknown pay excluded
    assert _qualifies(hi, 0, 0) is True                                                # no filter


def test_digest_filter_hides_below_threshold(cfg):
    led = Ledger.load(cfg)
    led.upsert({"job_id": "lo", "status": "ready_to_submit", "company": "A", "title": "Beauty Advisor",
                "url": "u", "fit_score": 0.5, "salary": "$20 an hour"})
    led.upsert({"job_id": "hi", "status": "ready_to_submit", "company": "B", "title": "Counter Manager",
                "url": "u", "fit_score": 0.7, "salary": "$34 an hour"})
    led.save()
    out = build_digest(led, min_fit=0.6, min_hourly=30)
    assert "Counter Manager" in out and "Beauty Advisor" not in out


def test_salary_line_render():
    assert _salary_line({"salary": "$50,000 a year"}) == "$50,000 a year"
    est = _salary_line({"salary": "$40k-$55k", "salary_estimated": True,
                        "salary_basis": "8 similar roles"})
    assert "estimated" in est and "8 similar roles" in est
    assert "not listed" in _salary_line({"salary": ""})


def test_digest_shows_salary_per_job(cfg):
    led = Ledger.load(cfg)
    led.upsert({"job_id": "1", "status": "ready_to_submit", "company": "Acme",
                "title": "Help Desk", "url": "u", "fit_score": 0.9,
                "ready_ts": "2026-06-25T00:00:00Z", "salary": "$48,000 a year"})
    led.save()
    assert "salary: $48,000 a year" in build_digest(led)


def test_salary_missing_lists_only_empty(cfg, capsys):
    led = Ledger.load(cfg)
    led.upsert({"job_id": "a", "status": "ready_to_submit", "title": "HD",
                "company": "C", "url": "u", "salary": "$50k"})
    led.upsert({"job_id": "b", "status": "ready_to_submit", "title": "DS",
                "company": "D", "url": "u2", "salary": ""})
    led.save()
    cmd_salary_missing(argparse.Namespace(status="ready_to_submit"), cfg)
    data = json.loads(capsys.readouterr().out)
    assert {d["job_id"] for d in data} == {"b"}


def test_report_heartbeat_when_nothing_new(cfg, capsys):
    from marceddy.cli import cmd_report
    # empty ledger -> nothing new; heartbeat on, no smtp creds -> printed only
    cmd_report(argparse.Namespace(email=True, heartbeat=True), cfg)
    out = capsys.readouterr().out
    assert "Nothing new" in out and "heartbeat" in out


def test_report_silent_without_heartbeat(cfg, capsys):
    from marceddy.cli import cmd_report
    cmd_report(argparse.Namespace(email=True, heartbeat=False), cfg)
    out = capsys.readouterr().out
    assert "No email sent" in out and "heartbeat" not in out


def test_salary_apply_merges_estimates(cfg, tmp_path):
    led = Ledger.load(cfg)
    led.upsert({"job_id": "j1", "status": "ready_to_submit", "company": "Acme",
                "title": "Help Desk", "url": "u", "salary": ""})
    led.save()
    est = tmp_path / "est.json"
    est.write_text(json.dumps({
        "j1": {"salary": "$44,000-$58,000 a year", "basis": "6 similar Columbus roles"}}))
    assert cmd_salary_apply(argparse.Namespace(file=str(est)), cfg) == 0
    r = Ledger.load(cfg).get("j1")
    assert r["salary"].startswith("$44,000")
    assert r["salary_estimated"] is True and "Columbus" in r["salary_basis"]
