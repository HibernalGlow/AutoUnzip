"""
命令行接口模块

使用 typer 提供现代化的命令行参数处理
"""

import typer
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path

from rich.console import Console
from ..analyzers.file_type_detector import DEFAULT_FILE_TYPES, ARCHIVE_EXTENSIONS

console = Console()

# 定义枚举类
class FileType(str, Enum):
    """支持的文件类型"""
    image = "image"
    video = "video"
    audio = "audio"
    document = "document"
    code = "code"
    archive = "archive"
    text = "text"
    font = "font"
    executable = "executable"
    model = "model"

class ArchiveType(str, Enum):
    """支持的压缩包类型"""
    zip = "zip"
    rar = "rar"
    seven_zip = "7z"
    tar = "tar"
    cbz = "cbz"
    cbr = "cbr"

# 创建 typer 应用
app = typer.Typer(help="自动解压工具 - 智能批量解压压缩包")


def merge_type_with_extensions(
    file_types: Optional[List[FileType]] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    use_include_mode: bool = True
) -> Dict[str, List[str]]:
    """将文件类型和扩展名列表合并
    
    Args:
        file_types: 指定的文件类型列表
        include: 包含的扩展名列表
        exclude: 排除的扩展名列表
        use_include_mode: 是否使用包含模式（默认True）
        
    Returns:
        Dict[str, List[str]]: 包含 'include' 和 'exclude' 键的字典
    """
    result_include = []
    result_exclude = []
    
    # 处理文件类型，根据模式将其转换为扩展名
    if file_types:
        type_extensions = []
        for file_type in file_types:
            extensions = DEFAULT_FILE_TYPES.get(file_type.value, set())
            # 移除点号前缀，因为用户通常不输入点号
            extensions = [ext.lstrip('.') for ext in extensions]
            type_extensions.extend(extensions)
        
        # 根据模式决定加入包含还是排除列表
        if use_include_mode:
            result_include.extend(type_extensions)
        else:
            result_exclude.extend(type_extensions)
    
    # 合并用户指定的扩展名
    if include:
        # 确保扩展名没有点号前缀
        include_clean = [ext.lstrip('.') for ext in include]
        result_include.extend(include_clean)
    
    if exclude:
        # 确保扩展名没有点号前缀
        exclude_clean = [ext.lstrip('.') for ext in exclude]
        result_exclude.extend(exclude_clean)
    
    return {
        'include': list(set(result_include)),  # 去重
        'exclude': list(set(result_exclude))   # 去重
    }

@app.command()
def main(
    # 位置参数
    target_path: Optional[str] = typer.Argument(
        None,
        help="要处理的文件或目录路径"
    ),
    
    # 基本选项
    path: Optional[str] = typer.Option(
        None, 
        "--path", 
        help="指定处理路径（与位置参数二选一）"
    ),
    clipboard: bool = typer.Option(
        False, 
        "--clipboard", "-c", 
        help="从剪贴板读取路径"
    ),
    
    # 解压选项
    delete_after: bool = typer.Option(
        False, 
        "--delete-after", "-d", 
        help="解压成功后删除源文件"
    ),
    password: Optional[str] = typer.Option(
        None, 
        "--password", "-p", 
        help="设置解压密码"
    ),
    prefix: str = typer.Option(
        "[#a]", 
        "--prefix", 
        help="解压文件夹前缀"
    ),
    
    # 递归和并行选项
    recursive: bool = typer.Option(
        False, 
        "--recursive", "-r", 
        help="递归处理嵌套压缩包"
    ),
    no_parallel: bool = typer.Option(
        False, 
        "--no-parallel", 
        help="禁用并行解压"
    ),
      # 文件过滤选项
    file_types: Optional[List[FileType]] = typer.Option(
        None, 
        "--types", "-t", 
        help="指定要处理的文件类型，配合 -i/-e 使用，默认为包含模式"
    ),
    include: Optional[List[str]] = typer.Option(
        None, 
        "--include", "-i", 
        help="包含模式：指定要包含的文件扩展名（不带点号）"
    ),
    exclude: Optional[List[str]] = typer.Option(
        None, 
        "--exclude", "-e", 
        help="排除模式：指定要排除的文件扩展名（不带点号）"
    ),
    
    # 压缩包类型过滤
    archive_types: Optional[List[ArchiveType]] = typer.Option(
        None, 
        "--archive-types", "-a", 
        help="指定要处理的压缩包格式"
    ),
    
    # 处理模式
    part: bool = typer.Option(
        False, 
        "--part", 
        help="启用部分解压模式：只提取符合过滤条件的文件，而不是跳过整个压缩包"
    ),
    
    # 界面选项
    tui: bool = typer.Option(
        False, 
        "--tui", 
        help="启用TUI图形配置界面"
    ),
    
    # 其他选项
    dzipfile: bool = typer.Option(
        False, 
        "--dzipfile", 
        help="禁用zipfile内容检查"
    ),
):
    """自动解压工具 - 智能批量解压压缩包"""    # 如果没有提供任何参数或明确请求TUI模式，启动TUI
    import sys
    if len(sys.argv) == 2 or tui:  # sys.argv[1] 是子命令名
        try:
            # 尝试导入并启动TUI模式
            from rich_preset import create_config_app
            from .config_manager import ConfigManager
            
            # 创建配置管理器
            config_manager = ConfigManager()
            preset_configs = config_manager.get_preset_configs()
            
            result = create_config_app(
                program=sys.argv[0],
                title="自动解压工具",
                parser=config_manager.parser,
                preset_configs=preset_configs,
            )
            
            # 处理参数
            from ..__main__ import run_with_params
            return run_with_params(result)
            
        except ImportError:
            console.print("[red]错误: 未找到 rich_preset 模块，无法启动TUI模式[/red]")
            console.print("[yellow]请使用命令行参数或安装必要的依赖[/yellow]")
            return 1
    
    # 确定目标路径
    final_path = target_path or path
    
    # 如果既没有位置参数也没有--path，且没有启用剪贴板模式，则显示帮助
    if not final_path and not clipboard:
        console.print("[yellow]请提供要处理的路径或使用 --clipboard 从剪贴板读取[/yellow]")
        console.print("使用 --help 查看更多选项")
        return 1
    
    # 确定模式：如果有 exclude 参数或者显式指定了 exclude 扩展名，使用排除模式
    has_exclude = exclude is not None and len(exclude) > 0
    has_include = include is not None and len(include) > 0
    
    # 决定使用包含还是排除模式
    if has_exclude and not has_include:
        # 只有排除参数，使用排除模式
        use_include_mode = False
    elif has_include and not has_exclude:
        # 只有包含参数，使用包含模式
        use_include_mode = True
    elif has_include and has_exclude:
        # 两者都有，优先使用包含模式，但会同时处理排除
        use_include_mode = True
    else:
        # 默认使用包含模式
        use_include_mode = True
    
    # 合并文件类型和扩展名
    merged_filters = merge_type_with_extensions(file_types, include, exclude, use_include_mode)
    
    # 显示合并后的过滤器信息（调试用）
    if merged_filters['include'] or merged_filters['exclude']:
        console.print("[blue]文件过滤设置:[/blue]")
        if merged_filters['include']:
            console.print(f"[green]包含: {', '.join(merged_filters['include'])}[/green]")
        if merged_filters['exclude']:
            console.print(f"[red]排除: {', '.join(merged_filters['exclude'])}[/red]")
    
    # 构建参数字典以兼容现有代码
    params = {
        'options': {
            '--delete-after': delete_after,
            '--clipboard': clipboard,
            '--recursive': recursive,
            '--no-parallel': no_parallel
        },        'inputs': {
            '--path': final_path or '',
            '--password': password or '',
            '--prefix': prefix
        },
        'filters': {
            '--include': merged_filters['include'],
            '--exclude': merged_filters['exclude'], 
            '--part': part,
            '--archive-types': [t.value for t in archive_types] if archive_types else []
        }
    }
    
    # 调用现有的处理函数
    from ..__main__ import run_with_params
    return run_with_params(params)


def get_typer_app():
    """获取 typer 应用实例"""
    return app


if __name__ == "__main__":
    app()
