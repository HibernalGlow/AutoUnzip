from __future__ import annotations
from rich.table import Table
from rich.console import Console
from .model import ScanResult
from .config import AppConfig

console = Console()

def build_table(result: ScanResult, cfg: AppConfig) -> Table:
    table = Table(title="grepu 扫描结果", show_lines=False)
    table.add_column("Archive", overflow="fold")
    table.add_column("Entry", overflow="fold")
    table.add_column("Reason", overflow="fold")
    for m in result.matches:
        table.add_row(m.archive, m.name, m.reason)
    # 补上无匹配与错误、缺失、禁用
    matched_archives = {m.archive for m in result.matches}
    for summary in result.summaries:
        if summary.error:
            table.add_row(summary.archive, "-", f"ERROR:{summary.error}")
            continue
        if summary.archive not in matched_archives:
            table.add_row(summary.archive, "-", "no-match")
        if summary.missing:
            table.add_row(summary.archive, "-", f"MISSING:{','.join(summary.missing)}")
        if summary.forbidden:
            table.add_row(summary.archive, "-", f"FORBIDDEN:{','.join(summary.forbidden)}")
    return table

def print_summary(result: ScanResult):
    console.print(
        f"[bold]统计[/bold] archives={result.total_archives()} matches={result.total_matches()} errors={result.total_errors()}"
    )
