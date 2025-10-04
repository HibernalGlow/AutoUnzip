from __future__ import annotations

"""Command line entry point for the grepu (7grep) utility."""

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .config import Config, load_config, write_default_config
from .core import (
    GrepuOptions,
    build_regex_pattern,
    build_ugrep_command,
    gather_archives,
    parse_extension_list,
)

console = Console()


@dataclass(slots=True)
class ExecutionContext:
    config: Config
    options: GrepuOptions
    seven_zip: str
    ugrep: str


class DependencyMissingError(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.init_config is not None:
        target = args.init_config or os.path.join(Path.home(), ".config", "grepu", "config.toml")
        path = write_default_config(target)
        console.print(f"[green]默认配置已写入[/green] {path}")
        return 0

    config = load_config(args.config)

    try:
        ctx = _build_context(args, config)
    except DependencyMissingError as error:
        console.print(f"[red]缺少依赖:[/red] {error}")
        return 1
    except ValueError as error:
        console.print(f"[red]参数错误:[/red] {error}")
        return 1

    if args.dry_run:
        command = build_ugrep_command(ctx.options)
        console.print("将执行命令:")
        console.print(Text.from_markup(f"[cyan]{_format_command(command)}[/cyan]"))
        return 0

    if not args.non_interactive:
        proceed = Confirm.ask("立即执行检索?", default=True)
        if not proceed:
            console.print("[yellow]已取消执行[/yellow]")
            return 0

    command = build_ugrep_command(ctx.options)
    console.print(Text.from_markup(f"[bold]执行 ugrep 命令:[/bold] [cyan]{_format_command(command)}[/cyan]"))

    ugrep_lines = _run_ugrep(command)
    console.print(f"[green]找到匹配文件 {len(ugrep_lines)} 个 (ugrep)[/green]")
    if ugrep_lines:
        for line in ugrep_lines:
            console.print(f"  • {line}")

    archive_summary = _analyze_archives(ctx.options, ctx.seven_zip)
    _render_archive_summary(archive_summary)

    console.print("[bold green]7grep 任务完成[/bold green]")
    return 0


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="7grep - 结合 7z 与 ugrep 的归档检索工具")
    parser.add_argument("--path", "-p", help="搜索根目录路径")
    parser.add_argument(
        "--archives",
        "-a",
        nargs="*",
        help="指定压缩包后缀 (多个使用空格分隔)",
    )
    parser.add_argument(
        "--formats",
        "-f",
        nargs="*",
        help="指定要匹配的文件后缀 (多个使用空格分隔)",
    )
    parser.add_argument("--config", "-c", help="配置文件路径 (toml)")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="跳过交互提示，直接使用配置或命令行参数",
    )
    parser.add_argument(
        "--ugrep-flag",
        dest="ugrep_flags",
        action="append",
        help="追加自定义 ugrep 参数 (可多次使用)",
    )
    parser.add_argument(
        "--init-config",
        nargs="?",
        const="",
        help="生成默认配置文件，可指定输出路径 (默认: ~/.config/grepu/config.toml)",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅展示即将执行的命令")
    return parser


def _build_context(args: argparse.Namespace, config: Config) -> ExecutionContext:
    search_path = _resolve_search_path(args, config)
    archive_formats = _resolve_archive_formats(args, config)
    search_extensions = _resolve_search_extensions(args, config)
    ugrep_flags = _resolve_ugrep_flags(args, config)

    seven_zip = _ensure_dependency("7z")
    ugrep = _ensure_dependency("ugrep")

    options = GrepuOptions(
        search_path=search_path,
        archive_formats=archive_formats,
        search_extensions=search_extensions,
        ugrep_flags=ugrep_flags,
    )

    return ExecutionContext(config=config, options=options, seven_zip=seven_zip, ugrep=ugrep)


def _resolve_search_path(args: argparse.Namespace, config: Config) -> Path:
    if args.path:
        candidate = Path(args.path).expanduser()
    elif args.non_interactive:
        candidate = Path(config.search_path).expanduser()
    else:
        answer = Prompt.ask("搜索路径", default=config.search_path)
        candidate = Path(answer or config.search_path).expanduser()

    if not candidate.exists():
        raise ValueError(f"路径不存在: {candidate}")
    return candidate


def _resolve_archive_formats(args: argparse.Namespace, config: Config) -> list[str]:
    if args.archives:
        result = parse_extension_list(args.archives)
    elif args.non_interactive:
        result = config.normalized_archive_suffixes()
    else:
        answer = Prompt.ask(
            "压缩包格式 (空格或逗号分隔)",
            default=", ".join(config.normalized_archive_suffixes()),
        )
        result = parse_extension_list(answer)
        if not result:
            result = config.normalized_archive_suffixes()
    if not result:
        raise ValueError("至少指定一种压缩包格式")
    return result


def _resolve_search_extensions(args: argparse.Namespace, config: Config) -> list[str]:
    if args.formats:
        result = parse_extension_list(args.formats)
    elif args.non_interactive:
        result = config.normalized_search_extensions()
    else:
        answer = Prompt.ask(
            "匹配文件格式 (空格或逗号分隔)",
            default=", ".join(config.normalized_search_extensions()),
        )
        result = parse_extension_list(answer)
        if not result:
            result = config.normalized_search_extensions()
    if not result:
        raise ValueError("至少指定一种匹配的文件格式")
    return result


def _resolve_ugrep_flags(args: argparse.Namespace, config: Config) -> list[str]:
    flags = list(config.ugrep_flags)
    if args.ugrep_flags:
        for flag in args.ugrep_flags:
            if flag:
                flags.append(flag)
    return flags


def _ensure_dependency(executable: str) -> str:
    path = shutil.which(executable)
    if path:
        return path
    raise DependencyMissingError(f"未找到可执行文件 `{executable}`，请先安装或配置环境变量")


def _run_ugrep(command: Sequence[str]) -> list[str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in (0, 1):
        raise RuntimeError(
            f"ugrep 执行失败 (退出码 {completed.returncode}): {completed.stderr.strip()}"
        )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return lines


@dataclass(slots=True)
class ArchiveReport:
    path: Path
    matches: int
    total_entries: int
    error_message: str | None = None


def _analyze_archives(options: GrepuOptions, seven_zip: str) -> list[ArchiveReport]:
    pattern_text = build_regex_pattern(options.search_extensions)
    archive_paths = gather_archives(options.search_path, options.archive_formats)
    reports: list[ArchiveReport] = []

    if not archive_paths:
        console.print("[yellow]未在目标路径中找到压缩包[/yellow]")
        return reports

    console.print(f"[bold]检测到 {len(archive_paths)} 个压缩包，正在统计匹配文件…[/bold]")
    compiled_pattern = re.compile(pattern_text, re.IGNORECASE)

    for archive in archive_paths:
        report = _analyze_single_archive(archive, seven_zip, compiled_pattern)
        reports.append(report)
    return reports


def _analyze_single_archive(
    archive: Path, seven_zip: str, pattern: re.Pattern[str]
) -> ArchiveReport:
    command = [seven_zip, "l", "-ba", str(archive)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        return ArchiveReport(
            path=archive,
            matches=0,
            total_entries=0,
            error_message=completed.stderr.strip() or "未知错误",
        )
    matches = 0
    total_entries = 0
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("---") or line.startswith("Date "):
            continue
        total_entries += 1
        if pattern.search(line):
            matches += 1
    return ArchiveReport(path=archive, matches=matches, total_entries=total_entries)


def _render_archive_summary(reports: Sequence[ArchiveReport]) -> None:
    if not reports:
        return

    table = Table(title="7z 统计结果")
    table.add_column("压缩包", overflow="fold")
    table.add_column("匹配数量", justify="right")
    table.add_column("总文件数", justify="right")
    table.add_column("状态")

    total_matches = 0
    total_entries = 0

    for report in reports:
        status = "✅ 成功" if report.error_message is None else f"❌ {report.error_message}"
        table.add_row(
            str(report.path),
            str(report.matches),
            str(report.total_entries),
            status,
        )
        total_matches += report.matches
        total_entries += report.total_entries

    table.add_section()
    table.add_row("总计", str(total_matches), str(total_entries), "")
    console.print(table)


def _format_command(command: Sequence[str]) -> str:
    return " ".join(_escape_segment(segment) for segment in command)


def _escape_segment(segment: str) -> str:
    if " " in segment or "\"" in segment:
        escaped = segment.replace("\"", "\\\"")
        return f'"{escaped}"'
    return segment


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断[/yellow]")
        raise SystemExit(0)
