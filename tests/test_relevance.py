from marceddy.models import Job
from marceddy.pipeline import is_relevant
from marceddy.profile import MASTER_PROFILE


def test_relevance_keeps_it_and_support():
    for title in ["IT Support Technician", "Help Desk Specialist",
                  "Junior Systems Administrator", "Network Engineer",
                  "Product Lead, Support Experience"]:
        j = Job(source="s", company="C", title=title, url="u")
        assert is_relevant(j, MASTER_PROFILE), title


def test_relevance_drops_non_it_noise():
    for title, desc in [
        ("Assistant Account Payable", "process invoices and vendor payments"),
        ("Office Assistant", "greet visitors, answer phones, schedule meetings"),
        ("Data Labeling Specialist", "label images for machine learning datasets"),
    ]:
        j = Job(source="s", company="C", title=title, url="u", description=desc)
        assert not is_relevant(j, MASTER_PROFILE), title
