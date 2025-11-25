from pathlib import Path
from typing import List, Optional

import tomllib
import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from encodeb.core import (
    find_suspicious,
    preview_file,
    preview_mappings,
    recover_file,
    recover_tree,
)
from encodeb.input import get_paths


console = Console()
app = typer.Typer(add_completion=False, help="EncodeB 名称修复和乱码扫描工具")


def _load_presets() -> dict[str, dict[str, str]]:
    candidates = [
        Path.cwd() / "encodeb_presets.toml",
        Path(__file__).with_name("presets.toml"),
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            with p.open("rb") as f:
                data = tomllib.load(f)
        except Exception:  # noqa: PERF203
            console.print(f"[red]预设配置文件解析失败：{p}[/]")
            return {}
        presets = data.get("presets")
        if isinstance(presets, dict):
            normalized: dict[str, dict[str, str]] = {}
            for name, cfg in presets.items():
                if isinstance(cfg, dict):
                    normalized[str(name)] = {
                        str(k): str(v) for k, v in cfg.items() if isinstance(k, str)
                    }
            return normalized
    return {}


@app.command("find")
def find_command(
    roots: List[Path] = typer.Argument(
        None,
        help="Paths (files or directories) to scan. Empty = use interactive / clipboard input.",
    ),
    limit: int = typer.Option(200, "--limit", help="Maximum number of results per root."),
    output_file: Optional[Path] = typer.Option(
        None,
        "-o",
        "--output-file",
        help="Write all matched paths (deduplicated) to this file, one per line.",
    ),
    output_clipboard: bool = typer.Option(
        False,
        "-oc",
        "--output-clipboard",
        help="Copy all matched paths (deduplicated) to clipboard as multi-line text.",
    ),
) -> None:
    """Scan for suspicious (likely garbled) names under given paths."""

    console.print("[bold cyan]EncodeB Find - 疑似乱码扫描[/]")

    if not roots:
        paths = get_paths()
        if not paths:
            console.print("[yellow]未获取到任何有效路径，已退出。[/]")
            raise typer.Exit(code=0)
        roots = [Path(p).expanduser() for p in paths]

    any_result = False
    all_matches: List[Path] = []

    for root in roots:
        if not root.exists():
            console.print(f"[red]路径不存在：{root}[/]")
            continue

        matches = find_suspicious(
            root=root,
            include_files=True,
            include_dirs=True,
            limit=limit,
        )

        console.print(f"[bold]扫描路径：[/]{root}")
        if matches:
            any_result = True
            all_matches.extend(matches)
            table = Table(title="疑似乱码名称 (最多 {0} 条)".format(limit))
            table.add_column("#", justify="right", style="cyan")
            table.add_column("类型", style="magenta")
            table.add_column("路径", overflow="fold")
            for idx, p in enumerate(matches, 1):
                kind = "目录" if p.is_dir() else "文件"
                table.add_row(str(idx), kind, str(p))
            console.print(table)
        else:
            console.print("[green]未发现疑似乱码名称。[/]")

    if not any_result:
        console.print("[yellow]所有路径均未检测到疑似乱码名称。[/]")
        raise typer.Exit(code=0)

    unique_paths: List[str] = []
    if output_file or output_clipboard:
        seen: set[str] = set()
        for p in all_matches:
            s = str(p)
            if s not in seen:
                seen.add(s)
                unique_paths.append(s)

    if output_file and unique_paths:
        out_path = output_file.expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        with out_path.open("w", encoding="utf-8") as f:
            for s in unique_paths:
                f.write(s + "\n")
        console.print(
            f"[green]已写入 {len(unique_paths)} 条路径到文件：[/][bold]{out_path}[/]"
        )

    if output_clipboard and unique_paths:
        try:
            import pyperclip

            pyperclip.copy("\n".join(unique_paths))
            console.print(
                f"[green]已将 {len(unique_paths)} 条路径复制到剪贴板。[/]"
            )
        except Exception as e:  # noqa: PERF203
            console.print(f"[red]复制到剪贴板失败：{e}[/]")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    roots: List[Path] = typer.Argument(
        None,
        help="Path(s) to files or directories containing garbled names.",
    ),
    src_encoding: Optional[str] = typer.Option(
        None,
        "--src-encoding",
        help="Encoding that was incorrectly used to decode the original bytes.",
    ),
    dst_encoding: Optional[str] = typer.Option(
        None,
        "--dst-encoding",
        help="Encoding that should be used to decode the original bytes (e.g. cp936, cp932).",
    ),
    preset: Optional[str] = typer.Option(
        None,
        "--preset",
        help="Name of preset defined in presets TOML (e.g. cn, jp).",
    ),
    no_preview: bool = typer.Option(
        False,
        "--no-preview",
        help="Skip interactive preview and execute directly.",
    ),
) -> None:
    """Default command: preview and recover names by copying to new files/directories."""

    if ctx.invoked_subcommand is not None:
        # A subcommand (e.g. find) was invoked; skip default behavior.
        return

    console.print("[bold cyan]EncodeB 名称修复工具[/]")

    if not roots:
        paths = get_paths()
        if not paths:
            console.print("[yellow]未获取到任何有效路径，已退出。[/]")
            raise typer.Exit(code=0)
        roots = [Path(p).expanduser() for p in paths]

    dir_roots: List[Path] = []
    file_roots: List[Path] = []
    for root in roots:
        if not root.exists():
            console.print(f"[red]路径不存在：{root}[/]")
            continue
        if root.is_dir():
            dir_roots.append(root)
        elif root.is_file():
            file_roots.append(root)
        else:
            console.print(f"[red]不支持的路径类型：{root}[/]")

    if not dir_roots and not file_roots:
        console.print("[red]没有可用的路径，已退出。[/]")
        raise typer.Exit(code=1)

    presets = _load_presets()

    src_enc = src_encoding
    dst_enc = dst_encoding

    if preset:
        preset_cfg = presets.get(preset)
        if not preset_cfg:
            if presets:
                available = ", ".join(sorted(presets.keys()))
                console.print(
                    f"[red]未找到预设：{preset}[/] 可用预设: [bold]{available}[/]"
                )
            else:
                console.print("[red]未找到任何预设配置文件。[/]")
            raise typer.Exit(code=1)
        if src_enc is None:
            src_enc = preset_cfg.get("src_encoding", src_enc)
        if dst_enc is None:
            dst_enc = preset_cfg.get("dst_encoding", dst_enc)

    if src_enc is None:
        src_enc = "cp437"
    if dst_enc is None:
        dst_enc = "cp936"

    if not no_preview:
        for root_path in dir_roots:
            mappings = preview_mappings(
                root=root_path,
                src_encoding=src_enc,
                dst_encoding=dst_enc,
                limit=50,
            )

            console.print(f"[bold]目录：[/]{root_path}")
            if mappings:
                table = Table(title="预览：名称重编码结果 (最多 50 条)")
                table.add_column("原路径", overflow="fold")
                table.add_column("新路径", overflow="fold")
                for src, dst in mappings:
                    table.add_row(str(src), str(dst))
                console.print(table)
            else:
                console.print("[yellow]没有检测到会变化的名称，预览为空。[/]")

        for file_path in file_roots:
            mappings = preview_file(
                path=file_path,
                src_encoding=src_enc,
                dst_encoding=dst_enc,
            )

            console.print(f"[bold]文件：[/]{file_path}")
            if mappings:
                table = Table(title="预览：文件名称重编码结果")
                table.add_column("原路径", overflow="fold")
                table.add_column("新路径", overflow="fold")
                for src, dst in mappings:
                    table.add_row(str(src), str(dst))
                console.print(table)
            else:
                console.print("[yellow]该文件名称不会发生变化。[/]")

        if not Confirm.ask("确认对以上路径执行复制并应用重命名吗？", default=True):
            console.print("[yellow]操作已取消。[/]")
            raise typer.Exit(code=0)

    for root_path in dir_roots:
        dest_root = recover_tree(
            root=root_path,
            src_encoding=src_enc,
            dst_encoding=dst_enc,
        )

        console.print(f"[green]已完成复制，输入目录：[/][bold]{root_path}[/]")
        console.print(f"[green]输出目录：[/][bold]{dest_root}[/]")

    for file_path in file_roots:
        dest_file = recover_file(
            path=file_path,
            src_encoding=src_enc,
            dst_encoding=dst_enc,
        )

        console.print(f"[green]已完成复制，输入文件：[/][bold]{file_path}[/]")
        console.print(f"[green]输出文件：[/][bold]{dest_file}[/]")


def main() -> None:  # CLI entry for setuptools
    app()


if __name__ == "__main__":  # pragma: no cover
    main()