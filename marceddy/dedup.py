"""Seen-store: remembers which job IDs MarcEddy has already processed.

This is what makes the hourly scan idempotent: a posting seen on a prior run is
skipped, so a re-run reports ``NEW: 0`` and produces no duplicate work.
"""
import json


class SeenStore:
    def __init__(self, path, ids=None):
        self.path = path
        self.ids = set(ids or [])

    @classmethod
    def load(cls, config):
        p = config.seen_path
        if p.exists():
            try:
                return cls(p, json.loads(p.read_text()))
            except Exception:
                return cls(p, [])
        return cls(p, [])

    def contains(self, jid):
        return jid in self.ids

    def add(self, jid):
        self.ids.add(jid)

    def save(self):
        self.path.write_text(json.dumps(sorted(self.ids), indent=2))
