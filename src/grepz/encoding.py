"""编码相关：当前策略固定使用 zipfile 返回的 str，不做重解码。
保留扩展点：未来可实现智能猜测。
"""
from __future__ import annotations

def normalize_name(name: str) -> str:
    # Placeholder: 未来可以在这里做 NFC 归一化 / 大小写策略
    return name
