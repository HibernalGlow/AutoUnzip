"""
图片元数据读取模块

支持快速读取图片分辨率，使用混合策略：
- 常见格式 (jpg/png/gif/webp/tiff): 使用 imagesize（10x 快于 Pillow）
- 新格式 (jxl/avif): 使用 Pillow + 插件

依赖：
    pip install imagesize pillow pillow-avif-plugin pillow-jxl-plugin
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple

# 图片扩展名分类
# imagesize 支持的格式
IMAGESIZE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.tiff', '.tif', 
    '.webp', '.svg', '.ppm', '.pgm', '.pbm', '.jp2', '.j2k'
}

# 需要 Pillow 的格式（新格式 + 不常见格式）
PILLOW_EXTENSIONS = {
    '.jxl',   # JPEG XL (需要 pillow-jxl-plugin)
    '.avif',  # AVIF (需要 pillow-avif-plugin)
    '.heic', '.heif',  # HEIC/HEIF
    '.bmp',   # BMP
    '.ico',   # ICO
    '.dds',   # DDS
    '.tga',   # TGA
    '.pcx',   # PCX
    '.psd',   # Photoshop
}

# 所有支持的图片扩展名
IMAGE_EXTENSIONS = IMAGESIZE_EXTENSIONS | PILLOW_EXTENSIONS


@dataclass
class ImageDimensions:
    """图片尺寸信息"""
    width: int
    height: int
    
    @property
    def resolution(self) -> str:
        """返回 WxH 格式的分辨率字符串"""
        return f"{self.width}x{self.height}"
    
    @property
    def megapixels(self) -> float:
        """返回百万像素数"""
        return (self.width * self.height) / 1_000_000
    
    @property
    def aspect_ratio(self) -> float:
        """返回宽高比"""
        if self.height == 0:
            return 0.0
        return self.width / self.height


def _get_dimensions_imagesize(filepath: str) -> Optional[Tuple[int, int]]:
    """使用 imagesize 库读取图片尺寸（快速）"""
    try:
        import imagesize
        width, height = imagesize.get(filepath)
        if width > 0 and height > 0:
            return (width, height)
        return None
    except ImportError:
        return None
    except Exception:
        return None


def _get_dimensions_pillow(filepath: str) -> Optional[Tuple[int, int]]:
    """使用 Pillow 读取图片尺寸（支持更多格式）"""
    try:
        # 尝试导入 Pillow 插件（如果可用）
        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pass
        
        try:
            import pillow_jxl  # noqa: F401
        except ImportError:
            pass
        
        from PIL import Image
        with Image.open(filepath) as img:
            return img.size
    except ImportError:
        return None
    except Exception:
        return None


def is_image_file(filepath: str) -> bool:
    """检查文件是否为支持的图片格式"""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in IMAGE_EXTENSIONS


def get_image_dimensions(filepath: str) -> Optional[ImageDimensions]:
    """
    获取图片的尺寸信息
    
    使用混合策略：
    1. 优先使用 imagesize（速度快）
    2. 回退到 Pillow（支持更多格式）
    
    Args:
        filepath: 图片文件路径
        
    Returns:
        ImageDimensions 对象，如果无法读取则返回 None
    """
    if not os.path.isfile(filepath):
        return None
    
    ext = os.path.splitext(filepath)[1].lower()
    
    # 不是图片文件
    if ext not in IMAGE_EXTENSIONS:
        return None
    
    dimensions = None
    
    # 策略1: 对于 imagesize 支持的格式，优先使用
    if ext in IMAGESIZE_EXTENSIONS:
        dimensions = _get_dimensions_imagesize(filepath)
    
    # 策略2: 如果 imagesize 失败或格式不支持，使用 Pillow
    if dimensions is None:
        dimensions = _get_dimensions_pillow(filepath)
    
    if dimensions:
        return ImageDimensions(width=dimensions[0], height=dimensions[1])
    
    return None


def get_image_dimensions_from_bytes(data: bytes, filename: str = "") -> Optional[ImageDimensions]:
    """
    从字节流获取图片尺寸信息（用于压缩包内的文件）
    
    Args:
        data: 图片文件的字节数据
        filename: 文件名（用于判断格式）
        
    Returns:
        ImageDimensions 对象，如果无法读取则返回 None
    """
    if not data:
        return None
    
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    
    # 不是图片文件
    if ext and ext not in IMAGE_EXTENSIONS:
        return None
    
    dimensions = None
    
    # 策略1: 尝试使用 imagesize（从字节流）
    if not ext or ext in IMAGESIZE_EXTENSIONS:
        try:
            import imagesize
            import io
            width, height = imagesize.get(io.BytesIO(data))
            if width > 0 and height > 0:
                dimensions = (width, height)
        except (ImportError, Exception):
            pass
    
    # 策略2: 使用 Pillow（从字节流）
    if dimensions is None:
        try:
            # 尝试导入 Pillow 插件
            try:
                import pillow_avif  # noqa: F401
            except ImportError:
                pass
            
            try:
                import pillow_jxl  # noqa: F401
            except ImportError:
                pass
            
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as img:
                dimensions = img.size
        except (ImportError, Exception):
            pass
    
    if dimensions:
        return ImageDimensions(width=dimensions[0], height=dimensions[1])
    
    return None


@lru_cache(maxsize=10000)
def get_image_dimensions_cached(filepath: str, mtime: float) -> Optional[ImageDimensions]:
    """
    获取图片尺寸（带缓存）
    
    Args:
        filepath: 图片文件路径
        mtime: 文件修改时间（用于缓存失效）
        
    Returns:
        ImageDimensions 对象
    """
    return get_image_dimensions(filepath)


def parse_resolution(resolution_str: str) -> Optional[Tuple[int, int]]:
    """
    解析分辨率字符串
    
    支持格式:
    - "1200x630" -> (1200, 630)
    - "1920X1080" -> (1920, 1080)
    - "800*600" -> (800, 600)
    
    Args:
        resolution_str: 分辨率字符串
        
    Returns:
        (width, height) 元组，解析失败返回 None
    """
    import re
    # 支持 x, X, * 作为分隔符
    match = re.match(r'^(\d+)[xX*](\d+)$', resolution_str.strip())
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return None


def resolution_matches(img_dims: ImageDimensions, target: str) -> bool:
    """
    检查图片尺寸是否匹配目标分辨率
    
    Args:
        img_dims: 图片尺寸
        target: 目标分辨率字符串（如 "1200x630"）
        
    Returns:
        是否匹配
    """
    parsed = parse_resolution(target)
    if parsed is None:
        return False
    return img_dims.width == parsed[0] and img_dims.height == parsed[1]
