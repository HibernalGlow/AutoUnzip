from __future__ import annotations

"""Core helper functions for grepu."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import re

__all__ = [
    "GrepuOptions",
    "parse_extension_list",
    "build_include_flags",
    "build_regex_pattern",
    "build_ugrep_command",
    "gather_archives",
]


@dataclass(slots=True)
class GrepuOptions:
    search_path: Path
    archive_formats: list[str]
    search_extensions: list[str]
    ugrep_flags: list[str]


def parse_extension_list(raw: str | Sequence[str] | None) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(";", ",").split(",")]
    else:
        parts = [str(item).strip() for item in raw]

    normalized = [part.lower().lstrip(".") for part in parts if part]
    return normalized


def build_include_flags(extensions: Sequence[str]) -> list[str]:
    return [f"--include=*.{ext}" for ext in extensions]


def build_regex_pattern(extensions: Sequence[str]) -> str:
    escaped = [re.escape(ext) for ext in extensions if ext]
    if not escaped:
        return r"\.\w+\b"
    joined = "|".join(escaped)
    return rf"\.({joined})\b"


def build_ugrep_command(options: GrepuOptions) -> list[str]:
    include_flags = build_include_flags(options.search_extensions)
    regex = build_regex_pattern(options.search_extensions)
    command = ["ugrep", *options.ugrep_flags, *include_flags, regex, str(options.search_path)]
    return command


def gather_archives(root: Path, archive_extensions: Iterable[str]) -> list[Path]:
    archives: list[Path] = []
    suffixes = {f".{ext.lower().lstrip('.')}" for ext in archive_extensions if ext}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in suffixes:
            archives.append(path)
    return archives
