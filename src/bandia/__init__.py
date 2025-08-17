"""bandia: 从剪贴板读取多个压缩包路径，调用 Bandizip 控制台工具 (bz.exe) 自动解压并在成功后删除源压缩包。
"""

__all__ = ["run"]

from .main import run
