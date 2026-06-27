from pathlib import Path

from marceddy.apply import prepare_applications, submit_applications
from marceddy.ledger import Ledger
from marceddy.pipeline import run_scan
from marceddy.profile import load_profile


def test_apply_prepares_every_fit_job(cfg):
    r = run_scan(cfg, source_name="fixture", verbose=False)
    assert r["fit"] >= 3
    profile = load_profile(cfg)

    prepared = prepare_applications(cfg, profile)
    assert len(prepared) == r["fit"]  # one application per fit job

    led = Ledger.load(cfg)
    ready = [x for x in led.all() if x.get("status") == "ready_to_submit"]
    assert len(ready) == r["fit"]
    for x in ready:
        assert x.get("apply_method") in ("email", "portal")
        assert x.get("cover_letter_path") and Path(x["cover_letter_path"]).exists()
        body = Path(x["cover_letter_txt"]).read_text()
        assert profile["name"] in body and x["title"] in body

    # idempotent: re-running prepares nothing new
    assert prepare_applications(cfg, profile) == []


def test_apply_submit_is_gated_off(cfg):
    run_scan(cfg, source_name="fixture", verbose=False)
    profile = load_profile(cfg)
    prepare_applications(cfg, profile)
    res = submit_applications(cfg, profile, do_submit=True)  # creds submit.enabled is false
    assert res["submitted"] == 0
    assert res["accounts_created"] == 0
    assert res["queued"] >= 3
