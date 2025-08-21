from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

@dataclass
class EntryMatch:
    archive: str
    name: str
    reason: str

@dataclass
class ArchiveSummary:
    archive: str
    match_count: int
    missing: list[str]
    forbidden: list[str]
    error: str | None = None

@dataclass
class ScanResult:
    matches: list[EntryMatch]
    summaries: list[ArchiveSummary]

    def total_archives(self) -> int:
        return len(self.summaries)

    def total_matches(self) -> int:
        return len(self.matches)

    def total_errors(self) -> int:
        return sum(1 for s in self.summaries if s.error)

    def to_dict(self):  # for JSON
        return {
            "matches": [m.__dict__ for m in self.matches],
            "summaries": [s.__dict__ for s in self.summaries],
            "stats": {
                "archives": self.total_archives(),
                "matches": self.total_matches(),
                "errors": self.total_errors(),
            },
        }
