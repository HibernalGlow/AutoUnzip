#!/usr/bin/env python
"""
批处理器 - 处理多个压缩包的批量操作

负责批量分析和解压压缩包。
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from rich.console import Console
from rich.prompt import Confirm

# 导入自定义模块
from autounzip.core.archive_analyzer import analyze_archive
from autounzip.core.zip_extractor import ZipExtractor, ExtractionResult

# 设置Rich控制台
console = Console()

class BatchProcessor:
    """批处理器，处理多个压缩包的批量操作"""
    
    def __init__(self, logger=None):
        """初始化批处理器"""
        self.logger = logger
    
    def analyze_archives(self, target_path: Union[str, Path]) -> Optional[str]:
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
            config_path = analyze_archive(target_path, display=True)
            
            return config_path
            
        except Exception as e:
            console.print(f"[red]分析压缩包时出错: {str(e)}[/red]")
            import traceback
            console.print(traceback.format_exc())
            return None
    
    def extract_archives(self, config_path: Union[str, Path], delete_after: bool = False) -> bool:
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
            zip_extractor = ZipExtractor()
            
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
    
    def run_with_params(self, params: Dict[str, Any]) -> int:
        """使用参数运行程序"""
        try:
            # 从参数中提取值
            delete_after = params['options'].get('--delete-after', False)
            folder_path = params['inputs'].get('--path', '')
            password = params['inputs'].get('--password', '')
            use_clipboard = params['options'].get('--clipboard', False)
            recursive = params['options'].get('--recursive', False)
            no_parallel = params['options'].get('--no-parallel', False)
            
            # 导入配置管理器
            from autounzip.core.config_manager import ConfigManager
            config_manager = ConfigManager()
            
            # 获取处理路径
            if use_clipboard:
                if self.logger:
                    self.logger.info("从剪贴板获取路径")
                folder_path = config_manager.get_path_from_clipboard()
            
            if not folder_path:
                console.print("[red]错误: 未指定有效的处理路径[/red]")
                console.print("使用 --path 指定路径或使用 --clipboard 从剪贴板读取路径")
                return 1
            
            # 分析压缩包
            if self.logger:
                self.logger.info(f"开始分析压缩包: {folder_path}")
            config_path = self.analyze_archives(folder_path)
            
            if not config_path:
                if self.logger:
                    self.logger.error("压缩包分析失败")
                return 1
            
            # 询问用户是否继续解压
            if Confirm.ask("[yellow]是否继续进行解压操作?[/yellow]", default=True):
                # 解压文件
                if self.logger:
                    self.logger.info(f"开始解压文件，配置文件: {config_path}")
                success = self.extract_archives(config_path, delete_after=delete_after)
                
                if success:
                    if self.logger:
                        self.logger.info("解压操作成功完成")
                    console.print("[green]✓ 解压操作成功完成！[/green]")
                    return 0
                else:
                    if self.logger:
                        self.logger.error("解压操作失败")
                    console.print("[red]✗ 解压操作失败[/red]")
                    return 1
            else:
                if self.logger:
                    self.logger.info("用户取消了解压操作")
                console.print("[yellow]已取消解压操作[/yellow]")
                return 0
                
        except KeyboardInterrupt:
            console.print("\n[yellow]程序被用户中断[/yellow]")
            return 1
        except Exception as e:
            console.print(f"[red]程序运行时出错: {str(e)}[/red]")
            import traceback
            console.print(traceback.format_exc())
            return 1
