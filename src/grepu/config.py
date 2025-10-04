from __future__ import annotations

"""Configuration loading utilities for the grepu package."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence
import os
import textwrap

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
    import tomli as tomllib  # type: ignore

__all__ = ["Config", "load_config", "write_default_config", "DEFAULT_CONFIG_TOML"]

DEFAULT_CONFIG_TOML = textwrap.dedent(
    """
    [defaults]
    search_path = "."
    archive_formats = ["zip", "rar", "7z"]
    search_extensions = ["jpg", "png", "gif"]

    [ugrep]
    flags = ["-r", "-U", "-l", "-i"]
    """
)


@dataclass(slots=True)
class Config:
    """Runtime configuration for the grepu command."""

    search_path: str = "."
    archive_formats: list[str] = field(default_factory=lambda: ["zip", "rar", "7z"])
    search_extensions: list[str] = field(default_factory=lambda: ["jpg", "png", "gif"])
    ugrep_flags: list[str] = field(default_factory=lambda: ["-r", "-U", "-l", "-i"])

    def normalized_archive_suffixes(self) -> list[str]:
        return _normalize_extensions(self.archive_formats)

    def normalized_search_extensions(self) -> list[str]:
        return _normalize_extensions(self.search_extensions)


def _normalize_extensions(extensions: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for ext in extensions:
        ext = ext.strip().lower()
        if not ext:
            continue
        if ext.startswith("."):
            ext = ext[1:]
        normalized.append(ext)
    return normalized


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from a candidate list of paths.

    Resolution order:
        1. explicit ``config_path`` argument
        2. ``GREPU_CONFIG`` environment variable
        3. ``~/.config/grepu/config.toml``
        4. packaged default configuration
    """

    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path).expanduser())

    env_path = os.environ.get("GREPU_CONFIG")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.append(Path.home() / ".config" / "grepu" / "config.toml")

    for candidate in candidates:
        if candidate.is_file():
            return _config_from_path(candidate)

    return _config_from_toml(DEFAULT_CONFIG_TOML)


def _config_from_path(path: Path) -> Config:
    raw = path.read_text(encoding="utf-8")
    return _config_from_toml(raw)


def _config_from_toml(content: str) -> Config:
    data = tomllib.loads(content)
    defaults = data.get("defaults", {})
    ugrep_section = data.get("ugrep", {})

    config = Config(
        search_path=str(defaults.get("search_path", ".")),
        archive_formats=_list_or_default(defaults.get("archive_formats"), ["zip", "rar", "7z"]),
        search_extensions=_list_or_default(defaults.get("search_extensions"), ["jpg", "png", "gif"]),
        ugrep_flags=_list_or_default(ugrep_section.get("flags"), ["-r", "-U", "-l", "-i"]),
    )
    return config


def _list_or_default(values: Iterable[str] | None, fallback: Iterable[str]) -> list[str]:
    if values is None:
        return list(fallback)
    return [str(item) for item in values]


def write_default_config(target_path: str | Path) -> Path:
    """Write the default configuration to ``target_path``.

    Creates parent directories if needed and returns the absolute path
    to the created file.
    """

    target = Path(target_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return target.resolve()
