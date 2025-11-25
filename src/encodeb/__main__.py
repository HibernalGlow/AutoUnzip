import argparse
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from encodeb.core import preview_file, preview_mappings, recover_file, recover_tree
from encodeb.input_path import get_paths


console = Console()


def main(argv: list[str] | None = None) -> int:

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
        default="cp437",
        help="Encoding that was incorrectly used to decode the original bytes.",
    )
    parser.add_argument(
        "--dst-encoding",
        default="cp936",
        help="Encoding that should be used to decode the original bytes (e.g. cp936, cp932).",
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

    src_enc = args.src_encoding
    dst_enc = args.dst_encoding

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