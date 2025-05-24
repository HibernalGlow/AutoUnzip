"""
压缩包信息数据类

定义压缩包的基本信息结构和解压模式常量
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any

# 解压模式常量
EXTRACT_MODE_ALL = "all"          # 解压所有文件
EXTRACT_MODE_SELECTIVE = "selective"  # 选择性解压
EXTRACT_MODE_SKIP = "skip"        # 跳过解压


@dataclass
class ArchiveInfo:
    """单个压缩包的信息"""
    path: str
    name: str
    parent_path: str = ""  # 父目录路径
    size: int = 0
    size_mb: float = 0.0
    extract_mode: str = EXTRACT_MODE_ALL  # 默认解压所有内容
    recommendation: str = ""
    file_count: int = 0
    file_types: Dict[str, int] = field(default_factory=dict)  # 文件类型统计
    file_extensions: Dict[str, int] = field(default_factory=dict)  # 文件扩展名统计
    dominant_types: List[str] = field(default_factory=list)  # 主要文件类型
    extract_path: str = ""  # 推荐的解压路径
    password_required: bool = False  # 是否需要密码
    password: str = ""  # 解压密码
    nested_archives: List["ArchiveInfo"] = field(default_factory=list)  # 嵌套的压缩包
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，便于JSON序列化"""
        from dataclasses import asdict
        result = asdict(self)
        # 移除嵌套对象，避免递归问题
        result.pop("nested_archives", None)
        return result
    
    def to_tree_dict(self) -> Dict[str, Any]:
        """转换为树结构的字典表示"""
        result = self.to_dict()
        # 添加嵌套压缩包信息
        if self.nested_archives:
            result["nested_archives"] = [nested.to_tree_dict() for nested in self.nested_archives]
        return result
