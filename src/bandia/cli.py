"""
bandia CLI - 使用 Typer 构建的命令行界面
支持子命令: extract, compress, repack

参考 mvz CLI 风格
"""

import json
from pathlib import Path
from typing import Annotated, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from .core import extract_batch, compress_batch
from .types import PathMapping, ExtractMode
from .utils import parse_text_paths, filter_archives, find_bz_executable

app = typer.Typer(
    name="bandia",
    help="批量解压/压缩工具 - 使用 Bandizip",
    add_completion=False,
)

console = Console()


def check_bz():
    """检查 Bandizip 是否可用"""
    if not find_bz_executable():
        console.print("[bold red]错误:[/bold red] 未找到 Bandizip (bz.exe)")
        console.print("请安装 Bandizip 或设置环境变量 BANDIZIP_PATH")
        raise typer.Exit(1)


@app.command("extract", help="解压压缩包")
def extract(
    paths: Annotated[Optional[List[str]], typer.Argument(help="压缩包路径列表")] = None,
    clipboard: Annotated[bool, typer.Option("--clipboard", "--clip", help="从剪贴板读取路径")] = False,
    delete: Annotated[bool, typer.Option("--delete/--keep", "-d/-k", help="解压后删除源文件")] = True,
    trash: Annotated[bool, typer.Option("--trash/--no-trash", "-t/-T", help="使用回收站")] = True,
    parallel: Annotated[bool, typer.Option("--parallel", "-P", help="启用并行解压")] = False,
    workers: Annotated[Optional[int], typer.Option("--workers", "-w", help="并行工作线程数")] = None,
    overwrite: Annotated[str, typer.Option("--overwrite-mode", "-o", help="冲突处理: overwrite/skip/rename")] = "overwrite",
    mode: Annotated[str, typer.Option("--mode", "-m", help="解压模式: auto(智能)/normal(普通)")] = "auto",
    prefix: Annotated[str, typer.Option("--prefix", "-p", help="普通模式输出目录前缀")] = "【a】",
    confirm: Annotated[bool, typer.Option("--confirm/--no-confirm", help="是否确认")] = True,
    output_json: Annotated[bool, typer.Option("--json", "-j", help="输出 JSON 格式结果（含路径映射）")] = False,
):
    """解压压缩包，支持批量操作和路径映射导出"""
    check_bz()
    
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
        console.print("[yellow]没有有效的压缩包路径[/yellow]")
        raise typer.Exit(1)
    
    # 解析解压模式
    extract_mode = ExtractMode.AUTO if mode == "auto" else ExtractMode.NORMAL
    mode_desc = "智能解压" if extract_mode == ExtractMode.AUTO else f"普通解压 (前缀: {prefix})"
    
    # 显示文件列表
    if not output_json:
        table = Table(title=f"待解压 ({len(collected)} 个) - {mode_desc}")
        table.add_column("#", justify="right", style="cyan", width=3)
        table.add_column("路径", style="magenta")
        for idx, p in enumerate(collected[:20], 1):
            table.add_row(str(idx), str(p))
        if len(collected) > 20:
            table.add_row("...", f"还有 {len(collected) - 20} 个")
        console.print(table)
    
    # 确认
    if confirm and not output_json:
        if not Confirm.ask("开始解压？", default=True):
            console.print("[yellow]已取消[/yellow]")
            raise typer.Exit(0)
    
    # 执行解压
    result = extract_batch(
        paths=collected,
        delete=delete,
        use_trash=trash,
        overwrite_mode=overwrite,
        parallel=parallel,
        workers=workers,
        extract_mode=extract_mode,
        output_prefix=prefix
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
    paths: Annotated[Optional[List[str]], typer.Argument(help="目录路径列表")] = None,
    output_dir: Annotated[Optional[str], typer.Option("--output", "-o", help="输出目录")] = None,
    delete: Annotated[bool, typer.Option("--delete/--keep", "-d/-k", help="压缩后删除源目录")] = True,
    format: Annotated[str, typer.Option("--format", "-f", help="压缩格式: zip/7z")] = "zip",
    confirm: Annotated[bool, typer.Option("--confirm/--no-confirm", help="是否确认")] = True,
):
    """压缩目录为压缩包"""
    check_bz()
    
    if not paths:
        console.print("[yellow]请提供要压缩的目录路径[/yellow]")
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
        console.print("[yellow]没有有效的目录[/yellow]")
        raise typer.Exit(1)
    
    # 显示列表
    table = Table(title=f"待压缩 ({len(mappings)} 个)")
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
    
    if confirm:
        if not Confirm.ask("开始压缩？", default=True):
            console.print("[yellow]已取消[/yellow]")
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
    mapping_file: Annotated[Optional[str], typer.Argument(help="路径映射 JSON 文件")] = None,
    clipboard: Annotated[bool, typer.Option("--clipboard", "--clip", help="从剪贴板读取映射 JSON")] = False,
    delete: Annotated[bool, typer.Option("--delete/--keep", "-d/-k", help="压缩后删除源目录")] = True,
    confirm: Annotated[bool, typer.Option("--confirm/--no-confirm", help="是否确认")] = True,
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
    check_bz()
    
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
        console.print("[yellow]请提供映射文件或使用 --clipboard[/yellow]")
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
        console.print("[yellow]没有有效的映射[/yellow]")
        raise typer.Exit(1)
    
    # 过滤存在的源目录
    valid_mappings = [m for m in mappings if Path(m.extracted_path).exists()]
    
    if not valid_mappings:
        console.print("[yellow]没有存在的源目录[/yellow]")
        raise typer.Exit(1)
    
    console.print(f"[cyan]找到 {len(valid_mappings)}/{len(mappings)} 个有效映射[/cyan]")
    
    # 显示列表
    table = Table(title="待重新压缩")
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
    
    if confirm:
        if not Confirm.ask("开始重新压缩？", default=True):
            console.print("[yellow]已取消[/yellow]")
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
        console.print(Panel.fit(
            "[bold cyan]bandia[/bold cyan] v2.1.0\n"
            "[dim]批量解压/压缩工具 - 使用 Bandizip[/dim]",
            border_style="cyan"
        ))
        raise typer.Exit(0)
    
    # 如果没有子命令，默认执行 extract（兼容旧行为）
    if ctx.invoked_subcommand is None:
        # 默认从剪贴板解压
        ctx.invoke(extract, clipboard=True)


if __name__ == "__main__":
    app()
