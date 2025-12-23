"""
findz 性能测试
测试大文件夹扫描性能和实时进度回调
"""

import os
import sys
import time
import pytest
from pathlib import Path

# 添加包路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from findz.filter.filter import create_filter
from findz.find.walk import walk, WalkParams, ProgressCallback


# 测试目录（可通过环境变量覆盖）
TEST_DIR = os.environ.get('FINDZ_TEST_DIR', r'E:\1Hub\EH\1EHV')


class ProgressTracker:
    """进度追踪器"""
    
    def __init__(self):
        self.scanned = 0
        self.matched = 0
        self.last_path = ""
        self.updates = 0
        self.start_time = time.time()
    
    def callback(self, scanned: int, matched: int, current_path: str):
        self.scanned = scanned
        self.matched = matched
        self.last_path = current_path
        self.updates += 1
        
        # 每次回调打印进度
        elapsed = time.time() - self.start_time
        speed = scanned / elapsed if elapsed > 0 else 0
        print(f"\r📊 扫描: {scanned:,} | 匹配: {matched:,} | 速度: {speed:,.0f}/s | {current_path[:50]:<50}", end="", flush=True)


@pytest.mark.skipif(not os.path.exists(TEST_DIR), reason=f"测试目录不存在: {TEST_DIR}")
class TestPerformance:
    """性能测试类"""
    
    def test_scan_all_files(self):
        """测试扫描所有文件（无过滤）"""
        print(f"\n\n🔍 测试目录: {TEST_DIR}")
        
        filter_expr = create_filter("1")  # 匹配所有
        tracker = ProgressTracker()
        
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=True,  # 不扫描压缩包内部
            use_cache=False,
            max_workers=4,
            progress_callback=tracker.callback,
            batch_size=500,
        )
        
        start = time.time()
        results = list(walk(TEST_DIR, params))
        elapsed = time.time() - start
        
        print(f"\n\n✅ 完成!")
        print(f"   总文件数: {len(results):,}")
        print(f"   扫描文件: {tracker.scanned:,}")
        print(f"   耗时: {elapsed:.2f}s")
        print(f"   速度: {len(results)/elapsed:,.0f} 文件/秒")
        print(f"   进度回调次数: {tracker.updates}")
        
        assert len(results) > 0, "应该找到文件"
        assert tracker.updates > 0, "应该有进度回调"
    
    def test_scan_with_filter(self):
        """测试带过滤条件扫描"""
        print(f"\n\n🔍 测试过滤扫描: {TEST_DIR}")
        
        # 只查找图片文件
        filter_expr = create_filter('ext in ("jpg", "jpeg", "png", "gif", "webp", "avif")')
        tracker = ProgressTracker()
        
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=True,
            use_cache=False,
            max_workers=4,
            progress_callback=tracker.callback,
        )
        
        start = time.time()
        results = list(walk(TEST_DIR, params))
        elapsed = time.time() - start
        
        print(f"\n\n✅ 完成!")
        print(f"   匹配文件: {len(results):,}")
        print(f"   扫描文件: {tracker.scanned:,}")
        print(f"   耗时: {elapsed:.2f}s")
        print(f"   速度: {tracker.scanned/elapsed:,.0f} 文件/秒")
    
    def test_scan_archives(self):
        """测试扫描压缩包内部"""
        print(f"\n\n🔍 测试压缩包扫描: {TEST_DIR}")
        
        filter_expr = create_filter("1")
        tracker = ProgressTracker()
        
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=False,  # 扫描压缩包内部
            use_cache=True,  # 使用缓存
            max_workers=4,
            progress_callback=tracker.callback,
            batch_size=100,  # 压缩包批量处理
        )
        
        start = time.time()
        results = list(walk(TEST_DIR, params))
        elapsed = time.time() - start
        
        print(f"\n\n✅ 完成!")
        print(f"   总文件数: {len(results):,}")
        print(f"   扫描文件: {tracker.scanned:,}")
        print(f"   耗时: {elapsed:.2f}s")
        print(f"   速度: {tracker.scanned/elapsed:,.0f} 文件/秒")


def run_quick_benchmark():
    """快速基准测试"""
    if not os.path.exists(TEST_DIR):
        print(f"❌ 测试目录不存在: {TEST_DIR}")
        return
    
    print(f"🚀 快速基准测试: {TEST_DIR}")
    print("=" * 60)
    
    filter_expr = create_filter("1")
    tracker = ProgressTracker()
    
    params = WalkParams(
        filter_expr=filter_expr,
        no_archive=True,
        use_cache=False,
        max_workers=4,
        progress_callback=tracker.callback,
    )
    
    start = time.time()
    count = 0
    for _ in walk(TEST_DIR, params):
        count += 1
    elapsed = time.time() - start
    
    print(f"\n\n{'=' * 60}")
    print(f"📊 结果:")
    print(f"   文件数: {count:,}")
    print(f"   耗时: {elapsed:.2f}s")
    print(f"   速度: {count/elapsed:,.0f} 文件/秒")


if __name__ == "__main__":
    run_quick_benchmark()
