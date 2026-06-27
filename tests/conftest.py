import pytest

from marceddy.config import Config


@pytest.fixture
def cfg(tmp_path):
    c = Config(home=str(tmp_path / "home"), account_email="you@example.com")
    c.ensure_dirs()
    return c
