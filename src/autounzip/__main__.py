#!/usr/bin/env python
"""
自动解压工具 - 简单版

负责处理命令行参数并调用相应的分析和解压功能。
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Union, Any
# 导入Rich库用于美化输出
from rich.console import Console
from rich.prompt import Confirm
# 导入预设模块
# from textual_preset import create_config_app

# 导入剪贴板模块（如果可用）
try:
    import pyperclip
except ImportError:
    pyperclip = None
    print("提示: 未安装pyperclip库，剪贴板功能将不可用")
    print("请使用: pip install pyperclip")

# 设置Rich控制台
console = Console()

# 设置日志记录器
from loguru import logger

def setup_logger(app_name="app", project_root=None, console_output=True):
    """配置 Loguru 日志系统
    
    Args:
        app_name: 应用名称，用于日志目录
        project_root: 项目根目录，默认为当前文件所在目录
        console_output: 是否输出到控制台，默认为True
        
    Returns:
        tuple: (logger, config_info)
            - logger: 配置好的 logger 实例
            - config_info: 包含日志配置信息的字典
    """
    # 获取项目根目录
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    
    # 清除默认处理器
    logger.remove()
    
    # 有条件地添加控制台处理器（简洁版格式）
    if console_output:
        logger.add(
            sys.stdout,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
    
    # 使用 datetime 构建日志路径
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    hour_str = current_time.strftime("%H")
    minute_str = current_time.strftime("%M%S")
    
    # 构建日志目录和文件路径
    log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{minute_str}.log")
    
    # 添加文件处理器
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,     )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

logger, config_info = setup_logger(app_name="auto_unzip", console_output=True)

# 配置常量
USE_RICH = True  # 默认使用Rich界面
EXTRACT_PARALLEL = True  # 默认并行解压

# 定义布局配置
TEXTUAL_LAYOUT = {
    "current_stats": {  # 总体进度面板
        "ratio": 2,     
        "title": "📊 总体进度",  
        "style": "lightyellow"  
    },
    "current_progress": {  # 当前进度面板
        "ratio": 2,
        "title": "🔄 当前进度",
        "style": "lightcyan"
    },
    "process": {  # 处理日志面板
        "ratio": 3,
        "title": "📝 处理日志",
        "style": "lightmagenta"
    },
    "update": {  # 更新日志面板
        "ratio": 2,
        "title": "ℹ️ 更新日志",
        "style": "lightblue"
    }
}

# 导入自定义模块
try:
    from autounzip.core.archive_analyzer import analyze_archive
except ImportError as e:
    console.print(f"[red]无法导入archive_analyzer模块: {str(e)}[/red]")

try:
    from autounzip.core.zip_extractor import ZipExtractor as extractor
except ImportError as e:
    console.print(f"[red]无法导入zip_extractor模块: {str(e)}[/red]")

def find_7zip_path():
    """尝试找到7-Zip的安装路径"""
    common_paths = [
        "C:\\Program Files\\7-Zip\\7z.exe",
        "C:\\Program Files (x86)\\7-Zip\\7z.exe",
        "D:\\Program Files\\7-Zip\\7z.exe"
    ]
    
    # 检查环境变量
    import shutil
    path_7z = shutil.which("7z")
    if path_7z:
        return path_7z
    
    # 检查常见位置
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return None


def get_path_from_clipboard():
    """从剪贴板获取路径，支持多行路径，返回第一个有效路径"""
    try:
        if pyperclip is None:
            console.print("[red]未安装pyperclip模块，请安装: pip install pyperclip[/red]")
            return ""
            
        clipboard_content = pyperclip.paste().strip()
        
        if not clipboard_content:
            console.print("[yellow]剪贴板内容为空[/yellow]")
            return ""
            
        # 处理多行路径，取第一个有效路径
        lines = clipboard_content.splitlines()
        valid_paths = []
        
        for line in lines:
            path = line.strip().strip('"').strip("'")
            if path and os.path.exists(path):
                valid_paths.append(path)
        
        if valid_paths:
            if len(valid_paths) > 1:
                console.print(f"[yellow]剪贴板包含多个路径，使用第一个有效路径: {valid_paths[0]}[/yellow]")
            return valid_paths[0]
        else:
            console.print("[yellow]剪贴板内容不包含有效路径[/yellow]")
            return ""
    except Exception as e:
        console.print(f"[red]从剪贴板获取路径时出错: {str(e)}[/red]")
        return ""

def analyze_archives(target_path: Union[str, Path], 
                    extract_prefix: str = "[#a]",
                    format_filters: dict = None,
                    archive_types: list = None,
                    flatten_single_folder: bool = False,
                    skip_codepage: bool = False) -> Optional[str]:
    """分析压缩包并返回JSON配置文件路径"""
    try:
        # 确保路径是Path对象
        target_path = Path(target_path) if isinstance(target_path, str) else target_path
        
        # 检查路径是否存在
        if not target_path.exists():
            console.print(f"[red]错误: 路径不存在: {target_path}[/red]")
            return None
        
        # 显示分析信息
        console.print(f"[blue]正在分析压缩包: {target_path}[/blue]")
        
        # 调用分析器
        config_path = analyze_archive(target_path, 
                                    display=True,
                                    extract_prefix=extract_prefix,
                                    format_filters=format_filters,
                                    archive_types=archive_types,
                                    flatten_single_folder=flatten_single_folder,
                                    skip_codepage=skip_codepage)
        
        return config_path
        
    except Exception as e:
        console.print(f"[red]分析压缩包时出错: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return None

def extract_archives(config_path: Union[str, Path], delete_after: bool = False) -> bool:
    """根据配置文件解压文件"""
    try:
        # 确保路径是Path对象
        config_path = Path(config_path) if isinstance(config_path, str) else config_path
        
        # 检查配置文件是否存在
        if not config_path.exists():
            console.print(f"[red]错误: 配置文件不存在: {config_path}[/red]")
            return False
        
        # 显示解压信息
        console.print(f"[blue]开始解压文件...[/blue]")
        
        # 创建解压器实例
        zip_extractor = extractor()
        
        # 调用解压器
        results = zip_extractor.extract_from_json(
            config_path=config_path, 
            delete_after_success=delete_after
        )
        
        # 统计成功和失败数量
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        
        # 显示结果
        if success_count > 0:
            console.print(f"[green]✓ 成功解压 {success_count} 个压缩包[/green]")
        
        if fail_count > 0:
            console.print(f"[red]✗ {fail_count} 个解压操作失败[/red]")
            for result in results:
                if not result.success:
                    console.print(f"[red]  - {os.path.basename(result.archive_path)}: {result.error_message}[/red]")
        
        return success_count > 0 and fail_count == 0
        
    except Exception as e:
        console.print(f"[red]解压文件时出错: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return False

def run_with_params(params: Dict[str, Any]) -> int:
    """使用参数运行程序"""
    try:
        # 检查params是否是rich_preset返回的特殊对象
        if hasattr(params, 'result'):
            # 这是一个ConfigResult对象，使用.result获取原始字典
            params = params.result
        
        # 从参数中提取值
        delete_after = params.get('options', {}).get('--delete-after', False)
        folder_path = params.get('inputs', {}).get('--path', '')
        password = params.get('inputs', {}).get('--password', '')
        use_clipboard = params.get('options', {}).get('--clipboard', False)
        recursive = params.get('options', {}).get('--recursive', False)
        no_parallel = params.get('options', {}).get('--no-parallel', False)
        flatten_single_folder = params.get('options', {}).get('--flatten-single-folder', False)
        skip_codepage = params.get('options', {}).get('--skip-codepage', False)
          # 提取新的过滤参数
        extract_prefix = params.get('inputs', {}).get('--prefix', '[#a]')
        format_filters = {}
        archive_types = []  # 初始化 archive_types 变量
          # 初始化默认值
        archive_types = []
        
        # 处理格式过滤参数（从 filters 部分获取）
        filters = params.get('filters', {})
        if filters:
            filters = params['filters']
            
            if '--formats' in filters and filters['--formats']:
                format_filters['--formats'] = filters['--formats']
            
            if '--include' in filters and filters['--include']:
                format_filters['--include'] = filters['--include']
                
            if '--exclude' in filters and filters['--exclude']:
                format_filters['--exclude'] = filters['--exclude']
                
            if '--type' in filters and filters['--type']:
                format_filters['--type'] = filters['--type']
                
            if '--part' in filters:
                format_filters['--part'] = filters['--part']
                
            # 处理压缩包类型过滤（也在 filters 部分）
            if '--archive-types' in filters and filters['--archive-types']:
                archive_types = filters['--archive-types']
        elif '--types' in params['inputs']:
            archive_types = params['inputs'].get('--types', [])or []
        
        # 获取处理路径
        if use_clipboard:
            logger.info("从剪贴板获取路径")
            folder_path = get_path_from_clipboard()
        
        if not folder_path:
            console.print("[red]错误: 未指定有效的处理路径[/red]")
            console.print("使用 --path 指定路径或使用 --clipboard 从剪贴板读取路径")
            return 1
          # 分析压缩包
        logger.info(f"开始分析压缩包: {folder_path}")
        config_path = analyze_archives(folder_path, extract_prefix, format_filters, archive_types, flatten_single_folder, skip_codepage)
        
        if not config_path:
            logger.info("未找到任何压缩包，程序正常结束")
            console.print("[yellow]未找到任何压缩包[/yellow]")
            return 0
        
        # 询问用户是否继续解压
        if Confirm.ask("[yellow]是否继续进行解压操作?[/yellow]", default=True):
            # 解压文件
            logger.info(f"开始解压文件，配置文件: {config_path}")
            success = extract_archives(config_path, delete_after=delete_after)
            
            if success:
                logger.info("解压操作成功完成")
                console.print("[green]✓ 解压操作成功完成！[/green]")
                return 0
            else:
                logger.error("解压操作失败")
                console.print("[red]✗ 解压操作失败[/red]")
                return 1
        else:
            logger.info("用户取消了解压操作")
            console.print("[yellow]已取消解压操作[/yellow]")            
            return 0
            
    except KeyboardInterrupt:
        console.print("\n[yellow]程序被用户中断[/yellow]")
        return 0
    except Exception as e:
        console.print(f"[red]程序运行时出错: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return 1


def main():
    """主函数"""
    try:
        # 使用 argparse CLI 和 ConfigManager
        from autounzip.core.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # 检查是否应该使用配置界面
        if config_manager.should_use_config_app():
            # 启动配置界面
            params = config_manager.launch_config_app()            
            if params:
                    return run_with_params(params)
            else:
                    console.print("[yellow]已取消操作[/yellow]")
                    return 0
        else:
            # 使用命令行参数
            params = config_manager.parse_command_line()
            return run_with_params(params)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]程序被用户中断[/yellow]")
        return 0
    except Exception as e:
        console.print(f"[red]程序运行时出错: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return 1
        
if __name__ == "__main__":
    sys.exit(main())


