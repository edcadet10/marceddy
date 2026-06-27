import os

from marceddy.apply import prepare_applications
from marceddy.autofill import ensure_demo_form, fill_application
from marceddy.ledger import Ledger
from marceddy.pipeline import run_scan
from marceddy.profile import load_profile


def _ready_row(cfg):
    run_scan(cfg, source_name="fixture", verbose=False)
    prepare_applications(cfg, load_profile(cfg))
    return [r for r in Ledger.load(cfg).all() if r.get("status") == "ready_to_submit"][0]


def test_autofill_fills_and_gate_holds(cfg):
    profile = load_profile(cfg)
    row = _ready_row(cfg)
    target = "file://" + str(ensure_demo_form(cfg))
    res = fill_application(cfg, profile, row, target, confirm=False)
    assert res["entered"].get("full_name") == profile["name"]
    assert "@" in res["entered"].get("email", "")
    assert os.path.exists(res["screenshot"])
    assert res["submitted"] is False  # no --confirm -> gate holds, nothing submitted


def test_autofill_confirm_submits_demo(cfg):
    profile = load_profile(cfg)
    row = _ready_row(cfg)
    target = "file://" + str(ensure_demo_form(cfg))
    res = fill_application(cfg, profile, row, target, confirm=True)
    assert res["submitted"] is True
