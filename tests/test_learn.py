from marceddy.policy import DEFAULT_POLICY, learn
from marceddy.profile import MASTER_PROFILE


def test_learn_bumps_version_and_policy():
    pol = dict(DEFAULT_POLICY)
    pol["version"] = 1
    outcomes = [
        {"company": "Initech Software", "status": "interview", "keywords": ["Python", "FastAPI"]},
        {"company": "Acme Cloud", "status": "rejected", "keywords": []},
        # a non-true keyword must NOT be added to tailoring
        {"company": "Quantum Co", "status": "interview", "keywords": ["Quantum"]},
    ]
    new_pol, log = learn(pol, outcomes, profile=MASTER_PROFILE)

    assert new_pol["version"] == 2
    assert log
    # threshold recalibrated (>=2 positives vs 1 negative -> widen net)
    assert new_pol["threshold"] < DEFAULT_POLICY["threshold"]
    # skills weight increased
    assert new_pol["weights"]["skills"] > DEFAULT_POLICY["weights"]["skills"]
    # weights still ~sum to 1
    assert abs(sum(new_pol["weights"].values()) - 1.0) < 1e-6
    # only TRUE skills added as tailoring keywords; "Quantum" excluded
    assert "Python" in new_pol["tailoring_keywords"]
    assert "FastAPI" in new_pol["tailoring_keywords"]
    assert "Quantum" not in new_pol["tailoring_keywords"]


def test_learn_no_outcomes_no_change():
    pol = dict(DEFAULT_POLICY)
    pol["version"] = 1
    new_pol, log = learn(pol, [], profile=MASTER_PROFILE)
    assert new_pol["version"] == 1
    assert log == []
