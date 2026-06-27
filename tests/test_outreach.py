"""Recruiter-outreach: tiered discovery, grounded email, hard send-gate. No network."""
import argparse
import json

from marceddy.creds import ensure_creds
from marceddy.ledger import Ledger
from marceddy.outreach import (_domain_from_url, discover_contact,
                               prepare_outreach, render_outreach_email, send_gate)

PROFILE = {
    "name": "Jeff Marc E. Cadet", "email": "you@example.com",
    "phone": "(215) 954-7673",
    "certifications": ["CompTIA A+", "CompTIA Network+ (N10-009)", "CompTIA Security+ (SY0-701)"],
    "skills": ["Help Desk", "Active Directory"],
}


def test_domain_from_url_skips_aggregators():
    assert _domain_from_url("https://careers.leidos.com/jobs/123") == "leidos.com"
    assert _domain_from_url("https://stripe.com/jobs/listing/x") == "stripe.com"
    assert _domain_from_url("https://to.indeed.com/aabbcc") == ""
    assert _domain_from_url("https://www.linkedin.com/jobs/view/123") == ""
    assert _domain_from_url("https://www.themuse.com/jobs/spacex/x") == ""


def test_discover_tier_apollo():
    contacts = {"SpaceX": {"found": True, "name": "Chris", "title": "Technical Recruiter",
                           "has_email": True}}
    c = discover_contact({"company": "SpaceX", "url": "https://www.themuse.com/jobs/spacex/x"}, contacts)
    assert c["tier"] == "apollo-recruiter"
    assert c["role"] == "Technical Recruiter" and c["name"] == "Chris"
    assert c["email"] == ""  # never revealed at discovery time (credits)


def test_discover_tier_careers_fallback():
    c = discover_contact({"company": "Leidos", "apply_target": "https://careers.leidos.com/jobs/9"}, {})
    assert c["tier"] == "company-careers-fallback"
    assert c["email"] == "careers@leidos.com" and c["email_verified"] is False


def test_discover_tier_none_for_aggregator():
    c = discover_contact({"company": "Centurum", "url": "https://to.indeed.com/x"}, {})
    assert c["tier"] == "none"


def test_job_boards_never_become_careers_email():
    # boards/ATS hosts must NOT yield a fabricated careers@ at the wrong domain
    for url in ("https://www.clearancejobs.com/jobs/123", "https://www.dice.com/job/x",
                "https://boards.greenhouse.io/acme/jobs/9", "https://acme.bamboohr.com/careers/1"):
        c = discover_contact({"company": "X", "apply_target": url}, {})
        assert c["tier"] == "none", url


def test_email_is_short_grounded_and_role_specific():
    row = {"title": "Help Desk Technician", "company": "Acme Corp",
           "match_keywords": "Active Directory, Ticketing"}
    contact = {"tier": "apollo-recruiter", "name": "Dana", "role": "Technical Recruiter"}
    subject, body = render_outreach_email(row, PROFILE, contact)
    assert len(body.split()) <= 150
    assert "Technical Recruiter" in body          # names the contact's role
    assert "Help Desk Technician" in body and "Acme Corp" in body  # specific job + company
    for cert in ("A+", "Network+", "Security+"):
        assert cert in body                       # cites real certs from profile
    assert "Jeff Marc E. Cadet" in body
    # nothing fabricated: no template placeholders left in
    assert "{" not in body and "TODO" not in body


def test_email_casual_when_voice_present():
    row = {"title": "Help Desk", "company": "Acme"}
    contact = {"tier": "none", "role": "Hiring Team"}
    _, formal = render_outreach_email(row, PROFILE, contact, voice=None)
    _, casual = render_outreach_email(row, PROFILE, contact, voice="hey, here's how I write")
    assert "Best regards" in formal and "Best regards" not in casual


def test_prepare_outreach_writes_drafts(cfg):
    ensure_creds(cfg)
    (cfg.home / "outreach_contacts.json").write_text(json.dumps(
        {"SpaceX": {"found": True, "name": "Chris", "title": "Technical Recruiter", "has_email": True}}))
    led = Ledger.load(cfg)
    led.upsert({"job_id": "a", "status": "ready_to_submit", "company": "SpaceX",
                "title": "IT Support Technician", "url": "https://www.themuse.com/jobs/spacex/x",
                "fit_score": 0.9, "tailored_resume_path": "/x/r.docx", "cover_letter_path": "/x/c.docx"})
    led.upsert({"job_id": "b", "status": "ready_to_submit", "company": "Leidos",
                "title": "Desktop Support", "apply_target": "https://careers.leidos.com/j/1",
                "url": "https://careers.leidos.com/j/1", "fit_score": 0.8})
    led.save()
    results = prepare_outreach(cfg, PROFILE, limit=5)
    assert len(results) == 2
    tiers = {r["company"]: r["tier"] for r in results}
    assert tiers["SpaceX"] == "apollo-recruiter"
    assert tiers["Leidos"] == "company-careers-fallback"
    for r in results:
        assert (cfg.home / "outreach").exists()
        assert r["word_count"] <= 150
        from pathlib import Path
        assert Path(r["email_path"]).exists()


def test_send_gate_dry_run(cfg, capsys):
    send_gate(argparse.Namespace(send=False), cfg, [])
    assert "dry-run: 0 emails" in capsys.readouterr().out


def test_send_gate_refuses_without_creds(cfg, capsys):
    ensure_creds(cfg)  # default outreach.enabled = False
    send_gate(argparse.Namespace(send=True), cfg, [])
    out = capsys.readouterr().out
    assert "refused" in out and "outreach.enabled is false" in out
