from marceddy.sources import FixtureSource, get_source


def test_fixture_returns_jobs():
    jobs = FixtureSource().fetch()
    assert len(jobs) >= 3
    for j in jobs:
        assert j.title and j.company and j.url
        assert j.job_id.startswith("fixture-")


def test_job_id_stable():
    a = FixtureSource().fetch()
    b = FixtureSource().fetch()
    assert [j.job_id for j in a] == [j.job_id for j in b]
    assert len({j.job_id for j in a}) == len(a)  # unique


def test_query_filter():
    jobs = FixtureSource().fetch(query="python")
    assert jobs
    assert all("python" in j.text_blob() for j in jobs)


def test_get_source_dispatch():
    assert get_source("fixture").name == "fixture"
    assert get_source("arbeitnow").name == "arbeitnow"
    assert get_source("remotive").name == "remotive"
