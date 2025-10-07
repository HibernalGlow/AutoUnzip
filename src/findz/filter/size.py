"""Size parsing and formatting utilities."""

import math
import re


def parse_size(size_str: str) -> int:
    """Parse a size string (e.g. '1G', '10M') and return size in bytes.
    
    Args:
        size_str: Size string with unit (B, K, M, G, T)
    
    Returns:
        Size in bytes as an integer
    
    Raises:
        ValueError: If the size string is invalid
    """
    units = {
        "B": 1,
        "K": 1 << 10,
        "M": 1 << 20,
        "G": 1 << 30,
        "T": 1 << 40,
    }
    
    size_str = size_str.upper().strip()
    
    # Match number followed by optional unit
    match = re.match(r"^([-+]?\d*\.?\d+)\s*([BKMGT])?$", size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    
    size_num = float(match.group(1))
    unit = match.group(2) or "B"
    
    return int(size_num * units[unit])


def format_size(size: int) -> str:
    """Format a size in bytes as a human-readable string.
    
    Args:
        size: Size in bytes
    
    Returns:
        Formatted size string (e.g. '1G', '10M')
    """
    if size == 0:
        return "0"
    
    units = ["", "K", "M", "G", "T", "P"]
    unit_index = int(math.log(abs(size)) / math.log(1024)) if size != 0 else 0
    
    if unit_index >= len(units):
        return str(size)
    
    value = size / (1024 ** unit_index)
    
    if value == int(value):
        return f"{int(value)}{units[unit_index]}"
    else:
        return f"{value:.1f}{units[unit_index]}"
