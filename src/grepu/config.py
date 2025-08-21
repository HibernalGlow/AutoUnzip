from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import tomllib

@dataclass
class MatchConfig:
    include_globs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    include_regex: list[str] = field(default_factory=list)
    exclude_regex: list[str] = field(default_factory=list)
    keywords_any: list[str] = field(default_factory=list)
    keywords_all: list[str] = field(default_factory=list)
    must_have: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)

@dataclass
class GeneralConfig:
    ignore_case: bool = True
    jobs: int = 4
    recursive: bool = False  # 目录递归扫描
    fail_fast: bool = False  # 首个错误立即停止 (未来扩展)
    short_circuit: bool = False  # 找到首个匹配就停止该压缩包后续遍历

@dataclass
class OutputConfig:
    color: bool = True
    short: bool = False
    json: bool = False
    summary: bool = True  # 输出末尾汇总

@dataclass
class AppConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    match: MatchConfig = field(default_factory=MatchConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def load_config(path: str | Path | None) -> AppConfig:
    if not path:
        return AppConfig()
    p = Path(path)
    if not p.is_file():
        return AppConfig()
    with p.open("rb") as f:
        data = tomllib.load(f)

    def build(section: str, cls):
        raw = data.get(section, {})
        base = cls()
        for k, v in raw.items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base

    return AppConfig(
        general=build("general", GeneralConfig),
        match=build("match", MatchConfig),
        output=build("output", OutputConfig),
    )
