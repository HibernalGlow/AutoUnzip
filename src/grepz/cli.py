from __future__ import annotations
import argparse, json
from rich.console import Console
from rich.progress import Progress
from .config import load_config, AppConfig
from .matcher import Matcher
from .runner import expand_targets, run_scan
from .output import build_table, print_summary

try:
    import pyperclip  # type: ignore
except Exception:  # pragma: no cover
    pyperclip = None

console = Console()


def parse_args():
    p = argparse.ArgumentParser("grepz", description="ZIP 内文件名匹配 (UTF-8 模式)")
    p.add_argument("paths", nargs="*", help="zip/目录 路径；为空尝试剪贴板")
    p.add_argument("-c", "--config", help="TOML 配置")
    p.add_argument("--jobs", type=int)
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--recursive", action="store_true", help="目录递归 *.zip")
    p.add_argument("--short-circuit", action="store_true", help="单包首个命中即停")
    p.add_argument("--must-have", action="append", default=[])
    p.add_argument("--must-not", action="append", default=[])
    # 直接传入模式（追加到配置）
    p.add_argument("--include-glob", action="append", default=[])
    p.add_argument("--exclude-glob", action="append", default=[])
    p.add_argument("--include-regex", action="append", default=[])
    p.add_argument("--exclude-regex", action="append", default=[])
    p.add_argument("--keyword-any", action="append", default=[])
    p.add_argument("--keyword-all", action="append", default=[])
    p.add_argument("--no-summary", action="store_true")
    return p.parse_args()


def gather_paths(args) -> list[str]:
    if args.paths:
        return args.paths
    if pyperclip:
        text = pyperclip.paste().strip()
        if text:
            return [ln.strip() for ln in text.splitlines() if ln.strip()]
    return []


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    # 覆盖/补充配置
    if args.jobs: cfg.general.jobs = args.jobs
    if args.ignore_case: cfg.general.ignore_case = True
    if args.no_color: cfg.output.color = False
    if args.json: cfg.output.json = True
    if args.recursive: cfg.general.recursive = True
    if args.short_circuit: cfg.general.short_circuit = True
    if args.no_summary: cfg.output.summary = False

    # 添加模式
    cfg.match.include_globs.extend([p for p in args.include_glob if p not in cfg.match.include_globs])
    cfg.match.exclude_globs.extend([p for p in args.exclude_glob if p not in cfg.match.exclude_globs])
    cfg.match.include_regex.extend([p for p in args.include_regex if p not in cfg.match.include_regex])
    cfg.match.exclude_regex.extend([p for p in args.exclude_regex if p not in cfg.match.exclude_regex])
    cfg.match.keywords_any.extend([p for p in args.keyword_any if p not in cfg.match.keywords_any])
    cfg.match.keywords_all.extend([p for p in args.keyword_all if p not in cfg.match.keywords_all])
    cfg.match.must_have.extend([p for p in args.must_have if p not in cfg.match.must_have])
    cfg.match.must_not.extend([p for p in args.must_not if p not in cfg.match.must_not])

    raw_paths = gather_paths(args)
    if not raw_paths:
        console.print("[red]未提供任何路径[/red]")
        return 1
    targets = expand_targets(raw_paths, cfg.general.recursive)
    if not targets:
        console.print("[yellow]未找到任何 zip 文件[/yellow]")
        return 1

    matcher = Matcher(cfg.match, cfg.general.ignore_case)
    with Progress() as progress:
        task = progress.add_task("扫描", total=len(targets))
        result = run_scan(targets, cfg, matcher)
        progress.update(task, completed=len(targets))

    if cfg.output.json:
        console.print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        table = build_table(result, cfg)
        console.print(table)
        if cfg.output.summary:
            print_summary(result)
    # 退出码策略：有错误 -> 2；有 forbidden -> 3；缺失 -> 4；否则 0
    any_forbidden = any(s.forbidden for s in result.summaries)
    any_missing = any(s.missing for s in result.summaries)
    if result.total_errors():
        return 2
    if any_forbidden:
        return 3
    if any_missing:
        return 4
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
