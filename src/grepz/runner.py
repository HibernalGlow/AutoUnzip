from __future__ import annotations
import concurrent.futures
from pathlib import Path
from typing import Iterable
import zipfile
from .config import AppConfig
from .matcher import Matcher
from .archive.zip_reader import iter_zip_entries
from .model import EntryMatch, ArchiveSummary, ScanResult


def expand_targets(paths: list[str], recursive: bool) -> list[str]:
    out: list[str] = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            out.append(str(path))
        elif path.is_dir() and recursive:
            for f in path.rglob("*.zip"):
                out.append(str(f))
    return out


def scan_archive(path: str, cfg: AppConfig, matcher: Matcher) -> tuple[list[EntryMatch], ArchiveSummary]:
    matches: list[EntryMatch] = []
    must_have_found: set[str] = set()
    must_not_found: set[str] = set()
    error: str | None = None
    try:
        for e in iter_zip_entries(path):
            details = matcher.check_entry(e.name)
            if details and details[0].matched:
                matches.append(EntryMatch(archive=path, name=e.name, reason=details[-1].reason))
                if cfg.general.short_circuit:
                    break
            # 包级
            for f in cfg.match.must_have:
                if e.name.endswith(f):
                    must_have_found.add(f)
            for f in cfg.match.must_not:
                if e.name.endswith(f):
                    must_not_found.add(f)
    except zipfile.BadZipFile:
        error = "BadZipFile"
    except Exception as ex:  # pragma: no cover
        error = f"{type(ex).__name__}:{ex}"  # noqa: E501
    missing = sorted(set(cfg.match.must_have) - must_have_found)
    forbidden = sorted(must_not_found)
    summary = ArchiveSummary(archive=path, match_count=len(matches), missing=missing, forbidden=forbidden, error=error)
    return matches, summary


def run_scan(paths: list[str], cfg: AppConfig, matcher: Matcher) -> ScanResult:
    all_matches: list[EntryMatch] = []
    summaries: list[ArchiveSummary] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.general.jobs) as ex:
        futures = [ex.submit(scan_archive, p, cfg, matcher) for p in paths]
        for fut in concurrent.futures.as_completed(futures):
            ms, sm = fut.result()
            all_matches.extend(ms)
            summaries.append(sm)
    return ScanResult(matches=all_matches, summaries=summaries)
