"""Configuration and on-disk paths for MarcEddy.

Everything MarcEddy persists lives under a single home directory (default
``~/.marceddy``, overridable with ``--home`` or ``MARCEDDY_HOME``). This keeps
the agent self-contained and easy to point at a temp dir during tests.
"""
import json
import os
from pathlib import Path

DEFAULT_ACCOUNT_EMAIL = "you@example.com"


class Config:
    def __init__(self, home=None, account_email=None):
        home = home or os.environ.get("MARCEDDY_HOME") or str(Path.home() / ".marceddy")
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.resumes_dir = self.home / "resumes"
        self.maildir = self.home / "maildir"
        self.policy_path = self.home / "policy.json"
        self.seen_path = self.home / "seen.json"
        self.ledger_json = self.home / "applications.json"
        self.ledger_csv = self.home / "applications.csv"
        self.creds_path = self.home / "credentials.json"
        self.state_path = self.home / "state.json"
        self.config_path = self.home / "config.json"
        self._account_email = account_email

    @property
    def account_email(self):
        if self._account_email:
            return self._account_email
        if self.config_path.exists():
            try:
                d = json.loads(self.config_path.read_text())
                if d.get("account_email"):
                    return d["account_email"]
            except Exception:
                pass
        return os.environ.get("MARCEDDY_ACCOUNT_EMAIL", DEFAULT_ACCOUNT_EMAIL)

    def ensure_dirs(self):
        self.resumes_dir.mkdir(parents=True, exist_ok=True)
        self.maildir.mkdir(parents=True, exist_ok=True)

    def load_state(self):
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except Exception:
                return {}
        return {}

    def save_state(self, state):
        self.state_path.write_text(json.dumps(state, indent=2))
