from rich.prompt import Prompt, Confirm
from rich.console import Console
from rich.table import Table
import pyperclip
import os
from loguru import logger
from typing import List, Optional

def get_path():
    """获取单个路径（保持向后兼容性）"""
    console = Console()
    path = Prompt.ask("请输入目标路径（留空则自动从剪贴板获取）")
    if not path:
        try:
            path = pyperclip.paste()
            logger.info(f"从剪贴板获取路径：{path}")
            console.print(f"[green]已从剪贴板获取路径：{path}")
        except Exception as e:
            logger.error(f"剪贴板读取失败: {e}")
            console.print(f"[red]剪贴板读取失败: {e}")
            return None
    path = path.strip('"')
    if not os.path.exists(path):
        logger.warning(f"路径无效: {path}")
        console.print(f"[red]路径无效: {path}")
        return None
    logger.info(f"使用路径: {path}")
    return path

def get_paths() -> Optional[List[str]]:
    """获取多个路径（支持单个或多个路径输入）"""
    console = Console()

    console.print("[bold blue]路径输入[/bold blue]")
    console.print("支持以下输入方式：")
    console.print("1. 从剪贴板获取多行路径")
    console.print("2. 手动逐个输入路径（输入空行结束）")
    console.print("3. 单个路径输入后直接回车结束")

    # 尝试从剪贴板获取
    clipboard_paths = []
    try:
        clipboard_content = pyperclip.paste().strip()
        if clipboard_content:
            # 按行分割剪贴板内容
            potential_paths = [line.strip().strip('"') for line in clipboard_content.split('\n') if line.strip()]

            # 验证路径
            valid_clipboard_paths = []
            for path in potential_paths:
                if os.path.exists(path):
                    valid_clipboard_paths.append(path)

            if valid_clipboard_paths:
                clipboard_paths = valid_clipboard_paths
                logger.info(f"从剪贴板获取到 {len(clipboard_paths)} 个有效路径")

                # 显示剪贴板路径预览
                console.print(f"\n[green]从剪贴板检测到 {len(clipboard_paths)} 个有效路径：[/green]")
                table = Table(show_header=True)
                table.add_column("序号", style="cyan")
                table.add_column("路径", style="green")

                for i, path in enumerate(clipboard_paths, 1):
                    table.add_row(str(i), path)

                console.print(table)

                if Confirm.ask("是否使用剪贴板中的路径？", default=True):
                    return clipboard_paths
    except Exception as e:
        logger.warning(f"剪贴板读取失败: {e}")
        console.print(f"[yellow]剪贴板读取失败: {e}[/yellow]")

    # 手动输入模式
    console.print("\n[blue]请输入文件夹路径（输入空行结束）：[/blue]")
    paths = []

    while True:
        if len(paths) == 0:
            path = Prompt.ask("路径", default="")
        else:
            path = Prompt.ask(f"路径 {len(paths) + 1}（留空结束）", default="")

        if not path:
            break

        path = path.strip().strip('"')

        if not os.path.exists(path):
            console.print(f"[red]路径不存在: {path}[/red]")
            continue

        if path in paths:
            console.print(f"[yellow]路径已存在: {path}[/yellow]")
            continue

        paths.append(path)
        console.print(f"[green]已添加路径 {len(paths)}: {path}[/green]")

    if not paths:
        logger.warning("未获取到任何有效路径")
        console.print("[yellow]未获取到任何有效路径[/yellow]")
        return None

    logger.info(f"获取到 {len(paths)} 个路径")
    return paths