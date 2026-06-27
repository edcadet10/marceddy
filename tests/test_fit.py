from marceddy.fit import meets, score_job
from marceddy.models import Job
from marceddy.policy import DEFAULT_POLICY
from marceddy.profile import MASTER_PROFILE
from marceddy.sources import FixtureSource

POLICY = DEFAULT_POLICY
PROFILE = MASTER_PROFILE


def test_on_target_job_scores_high():
    it_job = FixtureSource().fetch()[0]  # Northwind IT Support Specialist
    s = score_job(it_job, PROFILE, POLICY)
    assert s >= POLICY["threshold"]
    assert meets(it_job, PROFILE, POLICY)


def test_off_target_senior_job_scores_low():
    j = Job(source="x", company="BrandCo", title="Senior Marketing Manager",
            url="https://brandco.example/jobs/1", remote=False,
            description="Lead brand strategy and creative campaigns.")
    s = score_job(j, PROFILE, POLICY)
    assert s < POLICY["threshold"]
    assert not meets(j, PROFILE, POLICY)


def test_scoring_is_deterministic():
    j = FixtureSource().fetch()[0]
    assert score_job(j, PROFILE, POLICY) == score_job(j, PROFILE, POLICY)
