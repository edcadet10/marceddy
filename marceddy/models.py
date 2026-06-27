"""Core data types: a Job and helpers for stable IDs / slugs."""
import hashlib
import re
from dataclasses import dataclass, field


def slugify(s, maxlen=40):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = s[:maxlen].strip("-")
    return s or "na"


def short_hash(s, n=8):
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:n]


@dataclass
class Job:
    source: str
    company: str
    title: str
    url: str
    location: str = ""
    remote: bool = False
    description: str = ""
    tags: list = field(default_factory=list)
    posted_ts: str = ""
    ext_id: str = ""  # source-native id/slug, when available
    salary: str = ""              # human-readable, e.g. "$60,000–$72,000 a year"
    salary_estimated: bool = False  # True when researched rather than posting-listed
    salary_basis: str = ""        # how it was derived (listed / estimate rationale)

    @property
    def job_id(self):
        # Stable across runs: same posting -> same id -> dedup works.
        base = self.ext_id or self.url or f"{self.company}|{self.title}"
        return f"{self.source}-{short_hash(self.source + '::' + base)}"

    @property
    def company_slug(self):
        return slugify(self.company, 30)

    @property
    def role_slug(self):
        return slugify(self.title, 30)

    def text_blob(self):
        return " ".join([
            self.title or "", self.company or "", self.location or "",
            " ".join(self.tags or []), self.description or "",
        ]).lower()
