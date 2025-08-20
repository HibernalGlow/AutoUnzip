"""grepz: 纯 UTF-8 压缩包文件名匹配工具。

当前版本：仅支持 zip 文件；匹配支持 glob / 正则 / 关键词。
编码策略：永远以 UTF-8 读取；若 zip 条目未设置 UTF-8 位或实际并非 UTF-8，直接按原 zipfile 提供的字符串使用，不做额外再解码尝试。
"""

__all__ = [
    "load_config",
    "AppConfig",
]

from .config import load_config, AppConfig  # noqa: E402
