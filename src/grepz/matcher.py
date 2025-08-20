from __future__ import annotations
import fnmatch, re
from dataclasses import dataclass
from .config import MatchConfig

@dataclass
class MatchDetail:
    matched: bool
    reason: str
    pattern: str | None = None

class Matcher:
    def __init__(self, cfg: MatchConfig, ignore_case: bool = True):
        flags = re.IGNORECASE if ignore_case else 0
        self.cfg = cfg
        self.re_in = [re.compile(p, flags) for p in cfg.include_regex]
        self.re_ex = [re.compile(p, flags) for p in cfg.exclude_regex]
        self.ignore_case = ignore_case

    @staticmethod
    def _norm(name: str) -> str:
        return name.replace("\\", "/").strip("/")

    def _match_glob(self, name: str, patterns: list[str]):
        for p in patterns:
            if fnmatch.fnmatch(name, p):
                return p
        return None

    def check_entry(self, name: str) -> list[MatchDetail]:
        n = self._norm(name)
        cfg = self.cfg
        details: list[MatchDetail] = []
        if cfg.include_globs:
            p = self._match_glob(n, cfg.include_globs)
            if not p:
                return [MatchDetail(False, "no-include-glob")]
            details.append(MatchDetail(True, "include-glob", p))
        if cfg.exclude_globs and self._match_glob(n, cfg.exclude_globs):
            return [MatchDetail(False, "exclude-glob")]
        if self.re_in:
            if not any(r.search(n) for r in self.re_in):
                return [MatchDetail(False, "no-include-regex")]
            details.append(MatchDetail(True, "include-regex"))
        if any(r.search(n) for r in self.re_ex):
            return [MatchDetail(False, "exclude-regex")]
        lower = n.lower()
        if cfg.keywords_any:
            if not any(k.lower() in lower for k in cfg.keywords_any):
                return [MatchDetail(False, "no-keyword-any")]
            details.append(MatchDetail(True, "keyword-any"))
        if cfg.keywords_all:
            if not all(k.lower() in lower for k in cfg.keywords_all):
                return [MatchDetail(False, "no-keyword-all")]
            details.append(MatchDetail(True, "keyword-all"))
        return details or [MatchDetail(True, "pass")]
