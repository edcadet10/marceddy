import re

from marceddy.pipeline import run_scan


def test_scan_idempotency_and_resumes(cfg):
    r1 = run_scan(cfg, source_name="fixture", verbose=False)
    assert r1["found"] >= 5
    assert r1["new"] >= 3
    assert r1["tailored"] == r1["fit"]
    assert r1["fit"] >= 3

    # one tailored resume file per tailored job, named <company>_<role>_<jobid>.md
    resumes = sorted(cfg.resumes_dir.glob("*.docx"))
    assert len(resumes) == r1["tailored"]
    for p in resumes:
        assert re.match(r"^[a-z0-9-]+_[a-z0-9-]+_fixture-[0-9a-f]+\.docx$", p.name)

    # ledger has the required per-job fields
    import json
    rows = json.loads(cfg.ledger_json.read_text())
    for row in rows:
        for f in ["source", "company", "title", "url", "fit_score",
                  "tailored_resume_path", "status", "first_seen_ts", "account_email"]:
            assert f in row

    # second run: everything already seen -> NEW: 0, nothing tailored
    r2 = run_scan(cfg, source_name="fixture", verbose=False)
    assert r2["new"] == 0
    assert r2["tailored"] == 0
    assert len(list(cfg.resumes_dir.glob("*.docx"))) == r1["tailored"]


def test_submit_is_gated_off(cfg):
    # --submit without creds enabling it must submit nothing
    r = run_scan(cfg, source_name="fixture", submit=True, verbose=False)
    assert r["submitted"] == 0
