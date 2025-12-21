"""
高效缓存管理模块
支持 orjson（优先）和 pickle 序列化，增量 mtime 缓存
"""

import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# 尝试导入 orjson（比标准 json 快 10x）
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False


# 紧凑元组格式：(name, path, size, mtime_ts, type, container, archive, ext)
ResultTuple = Tuple[str, str, int, float, str, str, str, str]


class CacheManager:
    """
    缓存管理器
    
    功能：
    - 搜索结果缓存（orjson > pickle）
    - 目录 mtime 缓存（增量扫描）
    - 压缩包索引缓存
    """
    
    VERSION = 2  # 缓存版本号
    
    def __init__(self, cache_dir: Path = None):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录，默认 ~/.findz_cache
        """
        self.cache_dir = cache_dir or Path.home() / ".findz_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存文件路径
        self.result_cache_json = self.cache_dir / "results.json"  # orjson 格式
        self.result_cache_pkl = self.cache_dir / "results.pkl"    # pickle 备选
        self.dir_mtime_cache = self.cache_dir / "dir_mtime.json"  # 目录 mtime
        
        # 内存缓存
        self._dir_mtime: Dict[str, float] = {}
        self._load_dir_mtime()
    
    # ==================== 搜索结果缓存 ====================
    
    def save_results(
        self,
        results: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None
    ) -> None:
        """
        保存搜索结果到缓存
        
        优先使用 orjson（快 10x），备选 pickle
        不使用 indent 以节省空间和时间
        
        Args:
            results: 搜索结果列表（字典格式）
            metadata: 元数据（查询条件等）
        """
        # 转换为紧凑元组格式
        tuples = [self._dict_to_tuple(r) for r in results]
        
        cache_data = {
            'version': self.VERSION,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
            'count': len(tuples),
            'files': tuples,
        }
        
        if HAS_ORJSON:
            # orjson：最快，无 indent
            with open(self.result_cache_json, 'wb') as f:
                f.write(orjson.dumps(cache_data))
        else:
            # pickle：备选方案
            with open(self.result_cache_pkl, 'wb') as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    def load_results(self) -> Optional[Dict[str, Any]]:
        """
        加载搜索结果缓存
        
        Returns:
            缓存数据字典，包含 files（已转回字典格式）
        """
        cache_data = None
        
        # 优先尝试 orjson 格式
        if HAS_ORJSON and self.result_cache_json.exists():
            try:
                with open(self.result_cache_json, 'rb') as f:
                    cache_data = orjson.loads(f.read())
            except Exception:
                pass
        
        # 尝试 pickle 格式
        if cache_data is None and self.result_cache_pkl.exists():
            try:
                with open(self.result_cache_pkl, 'rb') as f:
                    cache_data = pickle.load(f)
            except Exception:
                pass
        
        if cache_data is None:
            return None
        
        # 检查版本
        if cache_data.get('version', 1) != self.VERSION:
            return None
        
        # 转换元组回字典格式
        files = cache_data.get('files', [])
        cache_data['files'] = [self._tuple_to_dict(t) for t in files]
        
        return cache_data
    
    def _dict_to_tuple(self, d: Dict[str, Any]) -> ResultTuple:
        """字典转紧凑元组"""
        # 处理 mtime：可能是 ISO 字符串或时间戳
        mtime = d.get('mod_time', '')
        if isinstance(mtime, str):
            try:
                mtime = datetime.fromisoformat(mtime).timestamp()
            except:
                mtime = 0.0
        elif not isinstance(mtime, (int, float)):
            mtime = 0.0
        
        return (
            d.get('name', ''),
            d.get('path', ''),
            d.get('size', 0),
            mtime,
            d.get('type', 'file'),
            d.get('container', ''),
            d.get('archive', ''),
            d.get('ext', ''),
        )
    
    def _tuple_to_dict(self, t: tuple) -> Dict[str, Any]:
        """元组转字典"""
        if len(t) < 8:
            # 兼容旧格式
            t = t + ('',) * (8 - len(t))
        
        mtime = datetime.fromtimestamp(t[3]) if t[3] else datetime.now()
        
        return {
            'name': t[0],
            'path': t[1],
            'size': t[2],
            'size_formatted': self._format_size(t[2]),
            'mod_time': mtime.isoformat(),
            'date': mtime.strftime("%Y-%m-%d"),
            'time': mtime.strftime("%H:%M:%S"),
            'type': t[4],
            'container': t[5],
            'archive': t[6],
            'ext': t[7],
        }
    
    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f}{unit}" if unit != 'B' else f"{size}B"
            size /= 1024
        return f"{size:.1f}PB"
    
    # ==================== 目录 mtime 缓存 ====================
    
    def _load_dir_mtime(self) -> None:
        """加载目录 mtime 缓存"""
        if not self.dir_mtime_cache.exists():
            return
        
        try:
            if HAS_ORJSON:
                with open(self.dir_mtime_cache, 'rb') as f:
                    self._dir_mtime = orjson.loads(f.read())
            else:
                import json
                with open(self.dir_mtime_cache, 'r', encoding='utf-8') as f:
                    self._dir_mtime = json.load(f)
        except Exception:
            self._dir_mtime = {}
    
    def _save_dir_mtime(self) -> None:
        """保存目录 mtime 缓存"""
        try:
            if HAS_ORJSON:
                with open(self.dir_mtime_cache, 'wb') as f:
                    f.write(orjson.dumps(self._dir_mtime))
            else:
                import json
                with open(self.dir_mtime_cache, 'w', encoding='utf-8') as f:
                    json.dump(self._dir_mtime, f)
        except Exception:
            pass
    
    def get_dir_mtime(self, path: str) -> Optional[float]:
        """获取缓存的目录 mtime"""
        return self._dir_mtime.get(path)
    
    def set_dir_mtime(self, path: str, mtime: float) -> None:
        """设置目录 mtime 缓存"""
        self._dir_mtime[path] = mtime
    
    def is_dir_changed(self, path: str) -> bool:
        """
        检查目录是否已修改
        
        Returns:
            True 如果目录已修改或不在缓存中
        """
        if not os.path.exists(path):
            return True
        
        cached_mtime = self.get_dir_mtime(path)
        if cached_mtime is None:
            return True
        
        try:
            current_mtime = os.stat(path).st_mtime
            return current_mtime != cached_mtime
        except OSError:
            return True
    
    def flush(self) -> None:
        """刷新所有缓存到磁盘"""
        self._save_dir_mtime()
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._dir_mtime.clear()
        
        for cache_file in [
            self.result_cache_json,
            self.result_cache_pkl,
            self.dir_mtime_cache,
        ]:
            if cache_file.exists():
                cache_file.unlink()


# 全局缓存实例
_global_cache: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager()
    return _global_cache
