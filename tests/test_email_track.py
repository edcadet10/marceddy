from marceddy.email_track import classify, link_and_update, parse_headers, scan_mailbox
from marceddy.ledger import Ledger
from marceddy.sources import PKG_DIR

MAILBOX = PKG_DIR / "data" / "mailbox"


def test_classify():
    assert classify("Interview invitation: IT Support at Northwind") == "interview"
    assert classify("Unfortunately we moved forward with others") == "rejected"
    assert classify("Re: Help Desk application status") == "replied"
    assert classify("Your weekly remote jobs digest") is None


def test_headers_only_no_body():
    p = sorted(MAILBOX.glob("*.eml"))[0]
    h = parse_headers(p)
    assert set(h.keys()) == {"from", "subject", "date", "path"}
    assert "body" not in h
    # no private body content leaks into the parsed metadata
    assert "PRIVATE BODY" not in (h["subject"] + h["from"] + h["date"])


def _seed_ledger(cfg):
    led = Ledger.load(cfg)
    for jid, comp, title, url in [
        ("fixture-nw", "Northwind Systems", "IT Support Specialist", "https://careers.northwind-systems.io/x"),
        ("fixture-ac", "Acme Cloud", "Help Desk Technician", "https://acmecloud.com/x"),
        ("fixture-gx", "Globex IT", "Junior Systems Administrator", "https://jobs.globex-it.com/x"),
    ]:
        led.upsert({"job_id": jid, "source": "fixture", "company": comp, "title": title,
                    "url": url, "fit_score": 0.9, "tailored_resume_path": "", "status": "tailored",
                    "first_seen_ts": "2026-06-24T00:00:00Z", "account_email": "you@example.com"})
    return led


def test_link_and_update(cfg):
    led = _seed_ledger(cfg)
    msgs = scan_mailbox(MAILBOX)
    changes = link_and_update(msgs, led, ts="2026-06-24T12:00:00Z")
    assert len(changes) >= 2
    by_company = {c["company"]: c for c in changes}
    assert by_company["Northwind Systems"]["new_status"] == "interview"
    assert by_company["Globex IT"]["new_status"] == "rejected"
    # before -> after recorded; no body anywhere in change dicts
    for c in changes:
        assert c["old_status"] == "tailored"
        assert "PRIVATE BODY" not in str(c)
        assert set(c.keys()) == {"company", "sender", "old_status", "new_status", "job_id"}
    # ledger actually updated
    assert led.get("fixture-nw")["status"] == "interview"
