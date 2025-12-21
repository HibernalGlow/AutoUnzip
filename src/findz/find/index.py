"""
倒排索引模块
用于快速过滤 archive 和 ext 字段
"""

import pickle
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

# 尝试导入 orjson
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False


class InvertedIndex:
    """
    倒排索引
    
    为 archive 和 ext 字段建立索引，支持快速查找
    """
    
    def __init__(self):
        # archive -> [file_indices]
        self.archive_index: Dict[str, List[int]] = defaultdict(list)
        # ext -> [file_indices]
        self.ext_index: Dict[str, List[int]] = defaultdict(list)
        # 文件总数
        self._count = 0
    
    def add(self, idx: int, archive: str, ext: str) -> None:
        """
        添加文件到索引
        
        Args:
            idx: 文件在结果列表中的索引
            archive: 压缩包路径
            ext: 文件扩展名
        """
        if archive:
            self.archive_index[archive].append(idx)
        if ext:
            ext_lower = ext.lower().lstrip('.')
            if ext_lower:
                self.ext_index[ext_lower].append(idx)
        self._count = max(self._count, idx + 1)
    
    def add_file(self, idx: int, file_dict: Dict[str, Any]) -> None:
        """
        从文件字典添加到索引
        
        Args:
            idx: 文件索引
            file_dict: 文件信息字典
        """
        archive = file_dict.get('archive', '') or file_dict.get('container', '')
        ext = file_dict.get('ext', '')
        self.add(idx, archive, ext)
    
    def get_by_archive(self, archive: str) -> List[int]:
        """
        按压缩包查找文件索引
        
        Args:
            archive: 压缩包路径
            
        Returns:
            文件索引列表
        """
        return self.archive_index.get(archive, [])
    
    def get_by_ext(self, ext: str) -> List[int]:
        """
        按扩展名查找文件索引
        
        Args:
            ext: 扩展名（不含点）
            
        Returns:
            文件索引列表
        """
        ext_lower = ext.lower().lstrip('.')
        return self.ext_index.get(ext_lower, [])
    
    def get_archives(self) -> Set[str]:
        """获取所有压缩包路径"""
        return set(self.archive_index.keys())
    
    def get_extensions(self) -> Set[str]:
        """获取所有扩展名"""
        return set(self.ext_index.keys())
    
    def count(self) -> int:
        """获取索引的文件总数"""
        return self._count
    
    def clear(self) -> None:
        """清空索引"""
        self.archive_index.clear()
        self.ext_index.clear()
        self._count = 0
    
    def save(self, path: Path) -> None:
        """
        保存索引到文件
        
        Args:
            path: 保存路径
        """
        data = {
            'archive': dict(self.archive_index),
            'ext': dict(self.ext_index),
            'count': self._count,
        }
        
        if HAS_ORJSON:
            with open(path, 'wb') as f:
                f.write(orjson.dumps(data))
        else:
            with open(path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    @classmethod
    def load(cls, path: Path) -> Optional['InvertedIndex']:
        """
        从文件加载索引
        
        Args:
            path: 索引文件路径
            
        Returns:
            InvertedIndex 实例，加载失败返回 None
        """
        if not path.exists():
            return None
        
        try:
            if HAS_ORJSON:
                with open(path, 'rb') as f:
                    data = orjson.loads(f.read())
            else:
                with open(path, 'rb') as f:
                    data = pickle.load(f)
            
            index = cls()
            index.archive_index = defaultdict(list, data.get('archive', {}))
            index.ext_index = defaultdict(list, data.get('ext', {}))
            index._count = data.get('count', 0)
            return index
            
        except Exception:
            return None
    
    @classmethod
    def build_from_files(cls, files: List[Dict[str, Any]]) -> 'InvertedIndex':
        """
        从文件列表构建索引
        
        Args:
            files: 文件信息字典列表
            
        Returns:
            构建好的 InvertedIndex
        """
        index = cls()
        for idx, f in enumerate(files):
            index.add_file(idx, f)
        return index
    
    def filter_by_archive(
        self,
        files: List[Dict[str, Any]],
        archive: str
    ) -> List[Dict[str, Any]]:
        """
        使用索引快速过滤指定压缩包的文件
        
        Args:
            files: 完整文件列表
            archive: 压缩包路径
            
        Returns:
            过滤后的文件列表
        """
        indices = self.get_by_archive(archive)
        return [files[i] for i in indices if i < len(files)]
    
    def filter_by_ext(
        self,
        files: List[Dict[str, Any]],
        ext: str
    ) -> List[Dict[str, Any]]:
        """
        使用索引快速过滤指定扩展名的文件
        
        Args:
            files: 完整文件列表
            ext: 扩展名
            
        Returns:
            过滤后的文件列表
        """
        indices = self.get_by_ext(ext)
        return [files[i] for i in indices if i < len(files)]


# 全局索引实例
_global_index: Optional[InvertedIndex] = None


def get_global_index() -> InvertedIndex:
    """获取全局索引实例"""
    global _global_index
    if _global_index is None:
        _global_index = InvertedIndex()
    return _global_index


def reset_global_index() -> None:
    """重置全局索引"""
    global _global_index
    _global_index = None
