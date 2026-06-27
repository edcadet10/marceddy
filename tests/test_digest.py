from marceddy.digest import build_digest
from marceddy.ledger import Ledger


def _seed(cfg):
    led = Ledger.load(cfg)
    rows = [
        ("a", "Northwind Systems", "interview", "2026-06-24T12:00:00Z"),
        ("b", "Acme Cloud", "replied", "2026-06-24T12:00:00Z"),
        ("c", "Globex IT", "rejected", "2026-06-24T12:00:00Z"),
        ("d", "Initech Software", "ready_to_submit", "2026-06-20T00:00:00Z"),
    ]
    for jid, comp, st, ts in rows:
        led.upsert({"job_id": jid, "source": "fixture", "company": comp, "title": "Role",
                    "url": "https://apply.example.com/" + jid, "fit_score": 0.8,
                    "tailored_resume_path": "", "status": st,
                    "first_seen_ts": ts, "last_update_ts": ts,
                    "account_email": "you@example.com", "last_email_from": "x@y.com",
                    "apply_target": "https://apply.example.com/" + jid})
    return led


def test_digest_actionable_and_sections(cfg):
    led = _seed(cfg)
    out = build_digest(led, state={"last_report_ts": "2026-06-21T00:00:00Z"})
    # actionable submit queue with a clickable apply link
    assert "ready to submit" in out
    assert "APPLY: https://apply.example.com/d" in out
    assert "Upcoming interviews: 1" in out
    # replied/interview/rejected updated after last_report_ts count as new replies
    assert "New replies since last run: 3" in out
