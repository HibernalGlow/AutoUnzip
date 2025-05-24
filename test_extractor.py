#!/usr/bin/env python3
"""
测试zip_extractor的新功能
"""

import sys
import os
import json
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from autounzip.core.zip_extractor import ZipExtractor
from rich.console import Console

console = Console()

def test_7z_wildcards():
    """测试7z通配符生成功能"""
    console.print("[blue]测试7z通配符生成功能...[/blue]")
    
    # 创建解压器实例
    extractor = ZipExtractor()
    
    # 测试包含模式的过滤配置
    test_config = {
        "--include": ["avif", "jpg", "png"],
        "--part": True
    }
    
    extractor.filter_config = test_config
    
    # 生成通配符
    wildcards = extractor._generate_7z_wildcards()
    
    console.print(f"过滤配置: {test_config}")
    console.print(f"生成的通配符: {wildcards}")
    
    expected_wildcards = ["*.avif", "*.jpg", "*.png"]
    
    if wildcards == expected_wildcards:
        console.print("[green]✓ 通配符生成测试通过[/green]")
        return True
    else:
        console.print(f"[red]✗ 通配符生成测试失败。期望: {expected_wildcards}, 实际: {wildcards}[/red]")
        return False

def test_filter_config_loading():
    """测试过滤配置加载功能"""
    console.print("[blue]测试过滤配置加载功能...[/blue]")
    
    config_path = Path("test_config.json")
    
    if not config_path.exists():
        console.print("[red]测试配置文件不存在[/red]")
        return False
    
    # 创建解压器实例
    extractor = ZipExtractor()
    
    # 读取配置文件
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        console.print(f"[red]读取配置文件失败: {e}[/red]")
        return False
    
    # 提取过滤配置
    filter_config = config.get("filter_config", {})
    extractor.filter_config = filter_config
    
    console.print(f"加载的过滤配置: {filter_config}")
    
    if filter_config:
        console.print("[green]✓ 过滤配置加载测试通过[/green]")
        return True
    else:
        console.print("[red]✗ 过滤配置加载测试失败[/red]")
        return False

def test_extract_mode_detection():
    """测试解压模式检测"""
    console.print("[blue]测试解压模式检测功能...[/blue]")
    
    # 导入FilterManager来测试
    try:
        from autounzip.analyzers.filter_manager import FilterManager
        
        # 测试部分解压模式
        config_part = {"--part": True, "--include": ["jpg", "png"]}
        filter_manager_part = FilterManager(config_part)
        
        part_mode = filter_manager_part.is_part_mode_enabled()
        console.print(f"部分解压模式配置: {config_part}")
        console.print(f"检测结果: {part_mode}")
        
        if part_mode:
            console.print("[green]✓ 部分解压模式检测正确[/green]")
        else:
            console.print("[red]✗ 部分解压模式检测失败[/red]")
            return False
        
        # 测试全量解压模式
        config_all = {"--part": False}
        filter_manager_all = FilterManager(config_all)
        
        all_mode = not filter_manager_all.is_part_mode_enabled()
        console.print(f"全量解压模式配置: {config_all}")
        console.print(f"检测结果: {all_mode}")
        
        if all_mode:
            console.print("[green]✓ 全量解压模式检测正确[/green]")
            return True
        else:
            console.print("[red]✗ 全量解压模式检测失败[/red]")
            return False
            
    except ImportError as e:
        console.print(f"[red]无法导入FilterManager: {e}[/red]")
        return False

def test_7z_command_building():
    """测试7z命令构建"""
    console.print("[blue]测试7z命令构建功能...[/blue]")
    
    # 这个测试主要检查命令是否能正确构建
    # 我们不会实际执行解压，只是测试命令构建逻辑
    
    extractor = ZipExtractor()
    extractor.filter_config = {
        "--include": ["jpg", "png"],
        "--part": True
    }
    
    # 测试通配符生成
    wildcards = extractor._generate_7z_wildcards()
    expected = ["*.jpg", "*.png"]
    
    if wildcards == expected:
        console.print(f"[green]✓ 7z通配符构建正确: {wildcards}[/green]")
        return True
    else:
        console.print(f"[red]✗ 7z通配符构建失败。期望: {expected}, 实际: {wildcards}[/red]")
        return False

def main():
    """运行所有测试"""
    console.print(Panel.fit("[bold blue]AutoUnzip 解压器测试[/bold blue]"))
    
    tests = [
        ("7z通配符生成", test_7z_wildcards),
        ("过滤配置加载", test_filter_config_loading),
        ("解压模式检测", test_extract_mode_detection),
        ("7z命令构建", test_7z_command_building),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        console.print(f"\n[cyan]运行测试: {test_name}[/cyan]")
        try:
            if test_func():
                passed += 1
                console.print(f"[green]✓ {test_name} 通过[/green]")
            else:
                console.print(f"[red]✗ {test_name} 失败[/red]")
        except Exception as e:
            console.print(f"[red]✗ {test_name} 出错: {e}[/red]")
            import traceback
            console.print(traceback.format_exc())
    
    console.print(f"\n[bold]测试结果: {passed}/{total} 通过[/bold]")
    
    if passed == total:
        console.print("[green]🎉 所有测试通过！[/green]")
        return 0
    else:
        console.print("[red]❌ 部分测试失败[/red]")
        return 1

if __name__ == "__main__":
    from rich.panel import Panel
    sys.exit(main())
