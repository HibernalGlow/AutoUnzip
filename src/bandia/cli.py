"""
bandia CLI - 使用 Typer 构建的命令行界面
支持子命令: extract, compress, repack
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from .core import extract_batch, compress_batch
from .types import PathMapping
from .utils import parse_text_paths, filter_archives

app = typer.Typer(
    name="bandia",
    help="批量解压/压缩工具 - 使用 Bandizip",
    add_completion=False
)

console = Console()


@app.command("extract", help="解压压缩包")
def extract(
    paths: List[str] = typer.Argument(None, help="压缩包路径列表"),
    clipboard: bool = typer.Option(False, "--clipboard", "-c", help="从剪贴板读取路径"),
    delete: bool = typer.Option(True, "--delete/--keep", "-d/-k", help="解压后删除源文件"),
    trash: bool = typer.Option(True, "--trash/--no-trash", "-t/-T", help="使用回收站"),
    parallel: bool = typer.Option(False, "--parallel", "-P", help="启用并行解压"),
    workers: Optional[int] = typer.Option(None, "--workers", "-w", help="并行工作线程数"),
    overwrite: str = typer.Option("overwrite", "--overwrite-mode", "-o", help="冲突处理: overwrite/skip/rename"),
    yes: bool = typer.Option(False, "--yes", "-y", help="非交互模式"),
    output_json: bool = typer.Option(False, "--json", "-j", help="输出 JSON 格式结果（含路径映射）"),
):
    """解压压缩包，支持批量操作和路径映射导出"""
    collected: List[Path] = []
    
    # 从剪贴板读取
    if clipboard:
        try:
            import pyperclip
            text = pyperclip.paste()
            parsed = parse_text_paths(text)
            if parsed:
                console.print(f"[green]从剪贴板读取 {len(parsed)} 个路径[/green]")
                collected.extend(parsed)
        except Exception as e:
            console.print(f"[red]读取剪贴板失败: {e}[/red]")
    
    # 从参数读取
    if paths:
        for p in paths:
            if Path(p).exists():
                collected.append(Path(p))
            else:
                # 尝试解析为文本
                parsed = parse_text_paths(p)
                collected.extend(parsed)
    
    # 默认行为：从剪贴板读取
    if not collected and not paths and not clipboard:
        try:
            import pyperclip
            text = pyperclip.paste()
            parsed = parse_text_paths(text)
            if parsed:
                console.print(f"[green]从剪贴板读取 {len(parsed)} 个路径[/green]")
                collected.extend(parsed)
        except Exception:
            pass
    
    # 去重
    seen = set()
    collected = [p for p in collected if not (p in seen or seen.add(p))]
    collected = filter_archives(collected)
    
    if not collected:
        console.print("[red]没有有效的压缩包路径[/red]")
        raise typer.Exit(1)
    
    # 显示文件列表
    if not output_json:
        table = Table(title=f"待解压 ({len(collected)} 个)", show_lines=False)
        table.add_column("#", justify="right", style="cyan", width=3)
        table.add_column("路径", style="magenta")
        for idx, p in enumerate(collected[:20], 1):
            table.add_row(str(idx), str(p))
        if len(collected) > 20:
            table.add_row("...", f"还有 {len(collected) - 20} 个")
        console.print(table)
    
    # 确认
    if not yes and not output_json:
        if not Confirm.ask("开始解压？", default=True):
            raise typer.Exit(0)
    
    # 执行解压
    result = extract_batch(
        paths=collected,
        delete=delete,
        use_trash=trash,
        overwrite_mode=overwrite,
        parallel=parallel,
        workers=workers
    )
    
    # 输出结果
    if output_json:
        output = {
            "success": result.success,
            "message": result.message,
            "extracted": result.extracted,
            "failed": result.failed,
            "total": result.total,
            "path_mappings": [
                {
                    "archive_path": str(r.path),
                    "extracted_path": str(r.output_path) if r.output_path else None
                }
                for r in result.results
                if r.success and r.output_path
            ]
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        console.print(f"\n[{'green' if result.success else 'yellow'}]{result.message}[/]")
    
    raise typer.Exit(0 if result.success else 1)


@app.command("compress", help="压缩目录")
def compress(
    paths: List[str] = typer.Argument(None, help="目录路径列表"),
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="输出目录"),
    delete: bool = typer.Option(True, "--delete/--keep", "-d/-k", help="压缩后删除源目录"),
    format: str = typer.Option("zip", "--format", "-f", help="压缩格式: zip/7z"),
    yes: bool = typer.Option(False, "--yes", "-y", help="非交互模式"),
):
    """压缩目录为压缩包"""
    if not paths:
        console.print("[red]请提供要压缩的目录路径[/red]")
        raise typer.Exit(1)
    
    mappings: List[PathMapping] = []
    
    for p in paths:
        source = Path(p)
        if not source.exists():
            console.print(f"[yellow]跳过不存在的路径: {p}[/yellow]")
            continue
        
        if output_dir:
            archive = Path(output_dir) / f"{source.name}.{format}"
        else:
            archive = source.parent / f"{source.name}.{format}"
        
        mappings.append(PathMapping(
            archive_path=str(archive),
            extracted_path=str(source)
        ))
    
    if not mappings:
        console.print("[red]没有有效的目录[/red]")
        raise typer.Exit(1)
    
    # 显示列表
    table = Table(title=f"待压缩 ({len(mappings)} 个)", show_lines=False)
    table.add_column("源目录", style="cyan")
    table.add_column("→", style="dim")
    table.add_column("目标", style="green")
    for m in mappings[:10]:
        table.add_row(
            Path(m.extracted_path).name,
            "→",
            Path(m.archive_path).name
        )
    if len(mappings) > 10:
        table.add_row("...", "", f"还有 {len(mappings) - 10} 个")
    console.print(table)
    
    if not yes:
        if not Confirm.ask("开始压缩？", default=True):
            raise typer.Exit(0)
    
    result = compress_batch(
        mappings=mappings,
        delete_source=delete,
        format=format
    )
    
    console.print(f"\n[{'green' if result.success else 'yellow'}]{result.message}[/]")
    raise typer.Exit(0 if result.success else 1)


@app.command("repack", help="根据路径映射重新压缩")
def repack(
    mapping_file: Optional[str] = typer.Argument(None, help="路径映射 JSON 文件"),
    clipboard: bool = typer.Option(False, "--clipboard", "-c", help="从剪贴板读取映射 JSON"),
    delete: bool = typer.Option(True, "--delete/--keep", "-d/-k", help="压缩后删除源目录"),
    yes: bool = typer.Option(False, "--yes", "-y", help="非交互模式"),
):
    """
    根据路径映射重新压缩（恢复原始压缩包）
    
    映射格式:
    {
        "mappings": [
            {"archive_path": "...", "extracted_path": "..."},
            ...
        ]
    }
    """
    mapping_json = None
    
    # 从剪贴板读取
    if clipboard:
        try:
            import pyperclip
            mapping_json = pyperclip.paste()
        except Exception as e:
            console.print(f"[red]读取剪贴板失败: {e}[/red]")
            raise typer.Exit(1)
    
    # 从文件读取
    elif mapping_file:
        try:
            mapping_json = Path(mapping_file).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[red]读取文件失败: {e}[/red]")
            raise typer.Exit(1)
    
    else:
        console.print("[red]请提供映射文件或使用 --clipboard[/red]")
        raise typer.Exit(1)
    
    # 解析 JSON
    try:
        data = json.loads(mapping_json)
        if isinstance(data, dict) and "mappings" in data:
            raw_mappings = data["mappings"]
        elif isinstance(data, list):
            raw_mappings = data
        else:
            raise ValueError("无效的映射格式")
        
        mappings = [
            PathMapping(
                archive_path=m["archive_path"],
                extracted_path=m["extracted_path"]
            )
            for m in raw_mappings
            if m.get("archive_path") and m.get("extracted_path")
        ]
    except Exception as e:
        console.print(f"[red]解析映射失败: {e}[/red]")
        raise typer.Exit(1)
    
    if not mappings:
        console.print("[red]没有有效的映射[/red]")
        raise typer.Exit(1)
    
    # 过滤存在的源目录
    valid_mappings = [m for m in mappings if Path(m.extracted_path).exists()]
    
    if not valid_mappings:
        console.print("[red]没有存在的源目录[/red]")
        raise typer.Exit(1)
    
    console.print(f"[cyan]找到 {len(valid_mappings)}/{len(mappings)} 个有效映射[/cyan]")
    
    # 显示列表
    table = Table(title="待重新压缩", show_lines=False)
    table.add_column("源目录", style="cyan")
    table.add_column("→", style="dim")
    table.add_column("目标压缩包", style="green")
    for m in valid_mappings[:10]:
        table.add_row(
            Path(m.extracted_path).name,
            "→",
            Path(m.archive_path).name
        )
    if len(valid_mappings) > 10:
        table.add_row("...", "", f"还有 {len(valid_mappings) - 10} 个")
    console.print(table)
    
    if not yes:
        if not Confirm.ask("开始重新压缩？", default=True):
            raise typer.Exit(0)
    
    result = compress_batch(
        mappings=valid_mappings,
        delete_source=delete
    )
    
    console.print(f"\n[{'green' if result.success else 'yellow'}]{result.message}[/]")
    raise typer.Exit(0 if result.success else 1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="显示版本"),
):
    """bandia - 批量解压/压缩工具"""
    if version:
        console.print("bandia v2.0.0")
        raise typer.Exit(0)
    
    # 如果没有子命令，默认执行 extract（兼容旧行为）
    if ctx.invoked_subcommand is None:
        # 默认从剪贴板解压
        ctx.invoke(extract, clipboard=True)


if __name__ == "__main__":
    app()
