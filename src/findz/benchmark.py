"""
findz 性能测试脚本
测试索引缓存和并行处理的性能提升
"""

import time
import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """运行命令并测量时间"""
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"命令: {cmd}")
    print(f"{'='*60}")
    
    start = time.time()
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    elapsed = time.time() - start
    
    # 提取找到的文件数
    output = result.stdout
    if "找到" in output:
        count_line = [line for line in output.split('\n') if "找到" in line]
        if count_line:
            print(count_line[0])
    
    print(f"耗时: {elapsed:.2f} 秒")
    
    if result.returncode != 0:
        print(f"错误: {result.stderr}")
    
    return elapsed

def main():
    """主测试函数"""
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    test_dir = str(Path(test_dir).absolute())
    
    print(f"\n{'#'*60}")
    print(f"# findz 性能测试")
    print(f"# 测试目录: {test_dir}")
    print(f"{'#'*60}")
    
    # 测试 1：基本搜索（无压缩包）
    print("\n\n## 测试 1: 基本文件搜索")
    cmd1 = f'python -m findz "ext = \'py\'" "{test_dir}" --no-archive'
    t1 = run_command(cmd1, "禁用压缩包支持")
    
    # 测试 2：启用压缩包（首次，无缓存）
    print("\n\n## 测试 2: 压缩包搜索（首次扫描）")
    # 先清除缓存
    cache_dir = Path.home() / ".findz_cache"
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        print("已清除缓存")
    
    cmd2 = f'python -m findz "ext = \'py\'" "{test_dir}"'
    t2 = run_command(cmd2, "首次扫描压缩包（建立缓存）")
    
    # 测试 3：启用压缩包（第二次，使用缓存）
    print("\n\n## 测试 3: 压缩包搜索（使用缓存）")
    cmd3 = f'python -m findz "ext = \'py\'" "{test_dir}"'
    t3 = run_command(cmd3, "再次搜索（使用缓存）")
    
    # 测试 4：并行处理（单线程）
    print("\n\n## 测试 4: 并行处理比较")
    # 先清除缓存
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
    
    cmd4 = f'python -m findz "ext = \'txt\'" "{test_dir}" -j 1'
    t4 = run_command(cmd4, "单线程处理")
    
    # 测试 5：并行处理（4线程）
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
    
    cmd5 = f'python -m findz "ext = \'txt\'" "{test_dir}" -j 4'
    t5 = run_command(cmd5, "4线程并行处理")
    
    # 测试 6：只搜索压缩包
    print("\n\n## 测试 6: 只搜索压缩包本身")
    cmd6 = f'python -m findz "size > 1K" "{test_dir}" --archives-only'
    t6 = run_command(cmd6, "只列出压缩包（不进入内部）")
    
    # 性能总结
    print(f"\n\n{'#'*60}")
    print(f"# 性能总结")
    print(f"{'#'*60}\n")
    
    print(f"1. 基本搜索（无压缩包）:     {t1:6.2f} 秒")
    print(f"2. 首次扫描压缩包:           {t2:6.2f} 秒")
    print(f"3. 使用缓存再次搜索:         {t3:6.2f} 秒")
    print(f"4. 单线程处理:              {t4:6.2f} 秒")
    print(f"5. 4线程并行处理:           {t5:6.2f} 秒")
    print(f"6. 只搜索压缩包（不进入）:   {t6:6.2f} 秒")
    
    print(f"\n性能提升:")
    if t2 > 0:
        speedup = (t2 / t3) if t3 > 0 else 0
        print(f"  缓存加速: {speedup:.1f}x")
    
    if t4 > 0:
        speedup = (t4 / t5) if t5 > 0 else 0
        print(f"  并行加速: {speedup:.1f}x")
    
    if t2 > 0:
        speedup = (t2 / t6) if t6 > 0 else 0
        print(f"  压缩包过滤加速: {speedup:.1f}x")

if __name__ == "__main__":
    main()
