from marceddy.ledger import LEDGER_FIELDS, Ledger

REQUIRED = ["source", "company", "title", "url", "fit_score",
            "tailored_resume_path", "status", "first_seen_ts", "account_email"]


def _row(jid="fixture-1"):
    return {"job_id": jid, "source": "fixture", "company": "Acme", "title": "Help Desk",
            "url": "https://acme/x", "fit_score": 0.9, "tailored_resume_path": "/tmp/r.md",
            "status": "tailored", "first_seen_ts": "2026-06-24T00:00:00Z",
            "account_email": "you@example.com", "last_update_ts": "2026-06-24T00:00:00Z"}


def test_required_fields_present():
    for f in REQUIRED:
        assert f in LEDGER_FIELDS


def test_upsert_and_update_status(cfg):
    led = Ledger.load(cfg)
    led.upsert(_row())
    assert led.get("fixture-1")["status"] == "tailored"
    # upsert again updates, does not duplicate
    led.upsert({"job_id": "fixture-1", "fit_score": 0.5})
    assert len(led.all()) == 1
    assert led.get("fixture-1")["fit_score"] == 0.5

    old = led.update_status("fixture-1", "interview", ts="2026-06-25T00:00:00Z")
    assert old == "tailored"
    assert led.get("fixture-1")["status"] == "interview"


def test_csv_and_persistence(cfg):
    led = Ledger.load(cfg)
    led.upsert(_row())
    led.save()
    csv_text = cfg.ledger_csv.read_text()
    for f in REQUIRED:
        assert f in csv_text.splitlines()[0]
    led2 = Ledger.load(cfg)
    assert led2.get("fixture-1")["company"] == "Acme"
