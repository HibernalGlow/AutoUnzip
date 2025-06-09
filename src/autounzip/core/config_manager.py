#!/usr/bin/env python
"""
配置管理器 - 处理AutoUnzip的配置和参数

负责处理命令行参数、配置文件和配置界面。
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

# 导入Rich库
from rich.console import Console
from rich.prompt import Confirm

# 导入预设模块
try:
    from textual_logger import TextualLoggerManager
except ImportError:
    pass

# 导入预设配置界面支持，优先使用rich_preset

from rich_preset import create_config_app

# from textual_preset import create_config_app 


# 剪贴板支持
try:
    import pyperclip
except ImportError:
    pyperclip = None

# 创建控制台
console = Console()

# 配置常量
USE_RICH = True  # 默认使用Rich界面
EXTRACT_PARALLEL = True  # 默认并行解压

class ConfigManager:
    """配置管理器，处理命令行参数和配置界面"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.parser = self.create_arg_parser()
        self.preset_configs = self.get_preset_configs()
    
    def create_arg_parser(self) -> argparse.ArgumentParser:
        """创建命令行参数解析器"""
        parser = argparse.ArgumentParser(description='文件自动解压工具')
        
        # 位置参数 - 目标路径
        parser.add_argument('target_path', nargs='?', 
                           help='要处理的文件或目录路径')
        
        # 解压选项
        parser.add_argument('--delete-after', '-d', action='store_true', 
                           help='解压成功后删除源文件')
        parser.add_argument('--prefix', type=str,
                           help='解压文件夹前缀')
        # 路径选项
        parser.add_argument('--clipboard', '-c', action='store_true', 
                           help='从剪贴板读取路径')
        parser.add_argument('--path', type=str, 
                           help='指定处理路径（与位置参数二选一）')        # TUI选项
        parser.add_argument('--tui', action='store_true',
                           help='启用TUI图形配置界面')
        parser.add_argument('--exit', action='store_true',
                           help='直接退出程序，返回码为0')
        
        # 递归和并行选项
        parser.add_argument('--recursive', '-r', action='store_true',
                           help='递归处理嵌套压缩包')
        parser.add_argument('--no-parallel', action='store_true',
                           help='禁用并行解压')
        parser.add_argument('--part', action='store_true',
                           help='启用部分解压模式：只提取符合过滤条件的文件，而不是跳过整个压缩包')
        
        # 其他选项
        parser.add_argument('--dzipfile', action='store_true', 
                           help='禁用zipfile内容检查')
        
        # 保留旧的参数用于兼容性
        parser.add_argument('-f', '--formats', nargs='+', 
                           help='文件格式筛选 (例如: jpg png avif)')
        # 文件过滤选项
        parser.add_argument('--types', '-t', nargs='+',
                           choices=['image', 'video', 'audio', 'document', 'code', 'archive', 'text'],
                           help='指定要处理的文件类型，配合 -i/-e 使用，默认为包含模式')
        parser.add_argument('-i', '--include', nargs='+',
                           help='包含模式：指定要包含的文件扩展名（不带点号）')
        parser.add_argument('-e', '--exclude', nargs='+', 
                           help='排除模式：指定要排除的文件扩展名（不带点号）')
        
        # 压缩包类型过滤
        parser.add_argument('-a', '--archive-types', nargs='+',
                           choices=['zip', 'rar', '7z', 'tar', 'cbz', 'cbr'],
                           help='指定要处理的压缩包格式')
        
        # 处理模式
        
        return parser
    def get_preset_configs(self) -> Dict[str, Any]:
        """获取预设配置"""        
        return {
            "无前缀解压": {
                "description": "无前缀解压模式",
                "checkbox_options": ["delete_after","clipboard"],
            },       
            "标准解压": {
                "description": "标准解压模式",
                "checkbox_options": ["delete_after","clipboard"],
                "input_values": {
                    "prefix": "[#a]",
                }
            },
            "安全退出": {
                "description": "安全退出模式",
                "checkbox_options": ["exit"],
            },        
            }

    def get_path_from_clipboard(self) -> str:
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
    def parse_command_line(self, args=None) -> Dict[str, Any]:
        """解析命令行参数，返回参数字典"""
        parsed_args = self.parser.parse_args(args)
        
        # 处理 --exit 参数
        if getattr(parsed_args, 'exit', False):
            console.print("[green]程序正常退出[/green]")
            sys.exit(0)
        
        # 处理路径参数 - 位置参数优先于--path选项
        target_path = getattr(parsed_args, 'target_path', None) or parsed_args.path or ''
        
        # 构建参数字典
        params = {
            'options': {
                '--delete-after': parsed_args.delete_after,
                '--clipboard': parsed_args.clipboard,
                '--recursive': parsed_args.recursive,
                '--no-parallel': getattr(parsed_args, 'no_parallel', False),
                '--part': getattr(parsed_args, 'part', False),
                '--dzipfile': getattr(parsed_args, 'dzipfile', False)
            },
            'inputs': {
                '--path': target_path,
                '--prefix': getattr(parsed_args, 'prefix', '[#a]')
            },
            'filters': {
                '--types': getattr(parsed_args, 'types', None) or [],
                '--include': getattr(parsed_args, 'include', None) or [],
                '--exclude': getattr(parsed_args, 'exclude', None) or [],
                '--formats': getattr(parsed_args, 'formats', None) or [],
                '--archive-types': getattr(parsed_args, 'archive_types', None) or [],
                '--part': getattr(parsed_args, 'part', False)
            }
        }
        
        return params
    
    def launch_config_app(self) -> Dict[str, Any]:
        """启动配置界面，返回用户选择的配置"""
        if create_config_app is None:
            console.print("[red]错误: 未找到配置界面支持模块[/red]")
            return None
        
        # 使用rich_preset版本的create_config_app
        if USE_RICH:
            result = create_config_app(
                program=sys.argv[0],
                title="自动解压工具",
                parser=self.parser,  # 使用命令行解析器自动生成选项
                preset_configs=self.preset_configs,  # 添加预设配置
            )
            return result
        else:
            # 使用Textual版本的create_config_app
            app = create_config_app(
                program=sys.argv[0],
                title="自动解压工具",
                parser=self.parser,
                preset_configs=self.preset_configs,
            )
            app.run()
            return app
    def should_use_config_app(self, args=None) -> bool:
        """判断是否应该使用配置界面"""
        # 如果没有传入args，检查sys.argv
        if args is None:
            # 检查是否有 --exit 参数
            if '--exit' in sys.argv:
                console.print("[green]程序正常退出[/green]")
                sys.exit(0)
            # 如果命令行参数为空或者明确指定--tui，使用配置界面
            return len(sys.argv) == 1 or '--tui' in sys.argv
        
        # 如果传入了参数列表，检查是否包含--tui或--exit
        if '--exit' in args:
            console.print("[green]程序正常退出[/green]")
            sys.exit(0)
        return len(args) == 0 or '--tui' in args
