import argparse
import sys
from pathlib import Path

import tomllib
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
from encodeb.input_path import get_paths


console = Console()


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


def _main_find(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="encodeb find",
        description=(
            "Scan directories and files for names that likely contain garbled "
            "characters (based on box-drawing and other unusual symbols)."
        ),
    )
    parser.add_argument(
        "root",
        type=str,
        nargs="*",
        help="Paths (files or directories) to scan. Empty = use interactive / clipboard input.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of results per root.",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        type=str,
        help="Write all matched paths (deduplicated) to this file, one per line.",
    )
    parser.add_argument(
        "-oc",
        "--output-clipboard",
        action="store_true",
        help="Copy all matched paths (deduplicated) to clipboard as multi-line text.",
    )

    args = parser.parse_args(argv)

    console.print("[bold cyan]EncodeB Find - 疑似乱码扫描[/]")

    roots: list[Path] = []
    if args.root:
        roots = [Path(p).expanduser() for p in args.root]
    else:
        paths = get_paths()
        if not paths:
            console.print("[yellow]未获取到任何有效路径，已退出。[/]")
            return 0
        roots = [Path(p).expanduser() for p in paths]

    any_result = False
    all_matches: list[Path] = []

    for root in roots:
        if not root.exists():
            console.print(f"[red]路径不存在：{root}[/]")
            continue

        matches = find_suspicious(
            root=root,
            include_files=True,
            include_dirs=True,
            limit=args.limit,
        )

        console.print(f"[bold]扫描路径：[/]{root}")
        if matches:
            any_result = True
            all_matches.extend(matches)
            table = Table(title="疑似乱码名称 (最多 {0} 条)".format(args.limit))

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
        return 0

    # 后处理：根据参数输出到文件或剪贴板
    unique_paths: list[str] = []
    if args.output_file or args.output_clipboard:
        seen: set[str] = set()
        for p in all_matches:
            s = str(p)
            if s not in seen:
                seen.add(s)
                unique_paths.append(s)

    if args.output_file and unique_paths:
        out_path = Path(args.output_file).expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 父目录可能已经存在，忽略错误
            pass
        with out_path.open("w", encoding="utf-8") as f:
            for s in unique_paths:
                f.write(s + "\n")
        console.print(
            f"[green]已写入 {len(unique_paths)} 条路径到文件：[/][bold]{out_path}[/]"
        )

    if args.output_clipboard and unique_paths:
        try:
            import pyperclip

            pyperclip.copy("\n".join(unique_paths))
            console.print(
                f"[green]已将 {len(unique_paths)} 条路径复制到剪贴板。[/]"
            )
        except Exception as e:  # noqa: PERF203
            console.print(f"[red]复制到剪贴板失败：{e}[/]")

    return 0


def main(argv: list[str] | None = None) -> int:

    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "find":
        return _main_find(argv[1:])

    parser = argparse.ArgumentParser(
        description=(
            "Recover garbled file and directory names by re-encoding "
            "from a source encoding to a destination encoding and copying "
            "to a new directory."
        )
    )
    parser.add_argument(
        "root",
        type=str,
        nargs="?",
        help="Path to the directory or file containing garbled names.",
    )
    parser.add_argument(
        "--src-encoding",
        default=None,
        help="Encoding that was incorrectly used to decode the original bytes.",
    )
    parser.add_argument(
        "--dst-encoding",
        default=None,
        help="Encoding that should be used to decode the original bytes (e.g. cp936, cp932).",
    )
    parser.add_argument(
        "--preset",
        type=str,
        help="Name of preset defined in presets TOML (e.g. cn, jp).",
    )

    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip interactive preview and execute directly.",
    )

    args = parser.parse_args(argv)

    console.print("[bold cyan]EncodeB 名称修复工具[/]")

    roots: list[Path] = []
    if args.root:
        roots = [Path(args.root).expanduser()]
    else:
        paths = get_paths()
        if not paths:
            console.print("[yellow]未获取到任何有效路径，已退出。[/]")
            return 0
        roots = [Path(p).expanduser() for p in paths]

    dir_roots: list[Path] = []
    file_roots: list[Path] = []
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
        return 1

    presets = _load_presets()

    src_enc = args.src_encoding
    dst_enc = args.dst_encoding

    if args.preset:
        preset = presets.get(args.preset)
        if not preset:
            if presets:
                available = ", ".join(sorted(presets.keys()))
                console.print(
                    f"[red]未找到预设：{args.preset}[/] 可用预设: [bold]{available}[/]"
                )
            else:
                console.print("[red]未找到任何预设配置文件。[/]")
            return 1
        if src_enc is None:
            src_enc = preset.get("src_encoding", src_enc)
        if dst_enc is None:
            dst_enc = preset.get("dst_encoding", dst_enc)

    if src_enc is None:
        src_enc = "cp437"
    if dst_enc is None:
        dst_enc = "cp936"

    if not args.no_preview:
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
            return 0

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


    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())