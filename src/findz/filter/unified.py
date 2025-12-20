"""
统一过滤器接口
支持 SQL 和 JSON 两种输入格式，输出统一的 FilterExpression

使用示例:
    # SQL 模式
    filter_expr = create_unified_filter('size > 10M and ext = "zip"')
    
    # JSON 模式
    filter_expr = create_unified_filter({
        "op": "and",
        "conditions": [
            {"field": "size", "op": ">", "value": "10M"},
            {"field": "ext", "op": "=", "value": "zip"}
        ]
    })
    
    # 自动检测
    filter_expr = create_unified_filter(input_str, auto_detect=True)
"""

import json
from typing import Any, Dict, Optional, Union

from .filter import FilterExpression, create_filter
from .json_filter import parse_json_filter, ast_to_json, PRESET_FILTERS
from .lang import parse_filter as parse_sql_filter


class FilterMode:
    """过滤器模式"""
    SQL = "sql"
    JSON = "json"
    AUTO = "auto"


def detect_filter_mode(input_data: Union[str, Dict, list]) -> str:
    """
    自动检测输入格式
    
    Args:
        input_data: 输入数据
    
    Returns:
        "sql" 或 "json"
    """
    # 字典或列表一定是 JSON
    if isinstance(input_data, (dict, list)):
        return FilterMode.JSON
    
    if not isinstance(input_data, str):
        return FilterMode.SQL
    
    input_str = input_data.strip()
    
    # 空字符串默认 SQL
    if not input_str:
        return FilterMode.SQL
    
    # 以 { 或 [ 开头，尝试 JSON
    if input_str.startswith(("{", "[")):
        try:
            json.loads(input_str)
            return FilterMode.JSON
        except json.JSONDecodeError:
            return FilterMode.SQL
    
    # 检查是否是预设名称
    if input_str.lower() in PRESET_FILTERS:
        return FilterMode.JSON
    
    # 默认 SQL
    return FilterMode.SQL


def create_unified_filter(
    input_data: Union[str, Dict, list],
    mode: str = FilterMode.AUTO,
) -> FilterExpression:
    """
    创建统一的过滤器表达式
    
    Args:
        input_data: 输入数据，可以是:
            - SQL 字符串: 'size > 10M and ext = "zip"'
            - JSON 字符串: '{"field": "size", "op": ">", "value": "10M"}'
            - JSON 字典/列表
            - 预设名称: "large_files", "images" 等
        mode: 解析模式
            - "auto": 自动检测
            - "sql": 强制 SQL 模式
            - "json": 强制 JSON 模式
    
    Returns:
        FilterExpression 对象
    
    Raises:
        ValueError: 解析失败
    """
    # 自动检测模式
    if mode == FilterMode.AUTO:
        mode = detect_filter_mode(input_data)
    
    # 处理预设
    if isinstance(input_data, str) and input_data.lower() in PRESET_FILTERS:
        input_data = PRESET_FILTERS[input_data.lower()]
        mode = FilterMode.JSON
    
    # 根据模式解析
    if mode == FilterMode.SQL:
        if not isinstance(input_data, str):
            raise ValueError("SQL 模式需要字符串输入")
        return create_filter(input_data)
    
    elif mode == FilterMode.JSON:
        ast = parse_json_filter(input_data)
        return FilterExpression(ast)
    
    else:
        raise ValueError(f"未知的模式: {mode}")


def sql_to_json(sql: str) -> Dict:
    """
    将 SQL 过滤器转换为 JSON 配置
    
    Args:
        sql: SQL 过滤字符串
    
    Returns:
        JSON 配置字典
    """
    ast = parse_sql_filter(sql)
    return ast_to_json(ast)


def json_to_sql(config: Union[str, Dict, list]) -> str:
    """
    将 JSON 配置转换为 SQL 字符串
    
    Args:
        config: JSON 配置
    
    Returns:
        SQL 过滤字符串
    """
    if isinstance(config, str):
        config = json.loads(config)
    
    return _json_to_sql_recursive(config)


def _json_to_sql_recursive(node: Union[Dict, list]) -> str:
    """递归转换 JSON 为 SQL"""
    # 列表转换为 AND 组
    if isinstance(node, list):
        node = {"op": "and", "conditions": node}
    
    # 条件组
    if "conditions" in node:
        op = node.get("op", "and").upper()
        conditions = node.get("conditions", [])
        negated = node.get("negated", False)
        
        if not conditions:
            return "1"  # 空条件 = 匹配所有
        
        parts = [_json_to_sql_recursive(c) for c in conditions]
        
        if len(parts) == 1:
            result = parts[0]
        else:
            result = f" {op} ".join(f"({p})" if " " in p else p for p in parts)
        
        if negated:
            result = f"NOT ({result})"
        
        return result
    
    # 单个条件
    field = node.get("field", "")
    op = node.get("op", "=").lower()
    value = node.get("value")
    
    # 格式化值
    def format_value(v):
        if isinstance(v, str):
            # 检查是否是特殊符号
            if v.lower() in ("today", "mo", "tu", "we", "th", "fr", "sa", "su"):
                return v.lower()
            # 检查是否是大小值
            if v and v[-1].upper() in "BKMGT":
                return v
            return f'"{v}"'
        elif isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        elif isinstance(v, (int, float)):
            return str(v)
        else:
            return f'"{v}"'
    
    # 根据运算符生成 SQL
    if op in ("=", "!=", "<>", "<", ">", "<=", ">="):
        return f"{field} {op} {format_value(value)}"
    
    elif op in ("like", "ilike", "rlike"):
        return f"{field} {op.upper()} {format_value(value)}"
    
    elif op in ("not_like", "not_ilike", "not_rlike"):
        actual_op = op.replace("not_", "").upper()
        return f"{field} NOT {actual_op} {format_value(value)}"
    
    elif op == "between":
        if isinstance(value, list) and len(value) >= 2:
            return f"{field} BETWEEN {format_value(value[0])} AND {format_value(value[1])}"
        value_end = node.get("value_end")
        return f"{field} BETWEEN {format_value(value)} AND {format_value(value_end)}"
    
    elif op == "not_between":
        if isinstance(value, list) and len(value) >= 2:
            return f"{field} NOT BETWEEN {format_value(value[0])} AND {format_value(value[1])}"
        value_end = node.get("value_end")
        return f"{field} NOT BETWEEN {format_value(value)} AND {format_value(value_end)}"
    
    elif op == "in":
        if not isinstance(value, list):
            value = [value]
        values_str = ", ".join(format_value(v) for v in value)
        return f"{field} IN ({values_str})"
    
    elif op == "not_in":
        if not isinstance(value, list):
            value = [value]
        values_str = ", ".join(format_value(v) for v in value)
        return f"{field} NOT IN ({values_str})"
    
    else:
        raise ValueError(f"未知的运算符: {op}")


# ============ 过滤器验证 ============

def validate_filter(
    input_data: Union[str, Dict, list],
    mode: str = FilterMode.AUTO,
) -> Dict[str, Any]:
    """
    验证过滤器配置
    
    Args:
        input_data: 输入数据
        mode: 解析模式
    
    Returns:
        验证结果:
        {
            "valid": bool,
            "mode": "sql" | "json",
            "error": str | None,
            "normalized": Dict | None  # JSON 格式的标准化配置
        }
    """
    result = {
        "valid": False,
        "mode": mode if mode != FilterMode.AUTO else None,
        "error": None,
        "normalized": None,
    }
    
    try:
        # 检测模式
        if mode == FilterMode.AUTO:
            mode = detect_filter_mode(input_data)
        result["mode"] = mode
        
        # 尝试解析
        filter_expr = create_unified_filter(input_data, mode)
        
        # 转换为标准化 JSON
        if mode == FilterMode.SQL and isinstance(input_data, str):
            result["normalized"] = sql_to_json(input_data)
        elif mode == FilterMode.JSON:
            # 已经是 JSON，直接使用
            if isinstance(input_data, str):
                result["normalized"] = json.loads(input_data)
            else:
                result["normalized"] = input_data
        
        result["valid"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


# ============ 导出 ============

__all__ = [
    "FilterMode",
    "detect_filter_mode",
    "create_unified_filter",
    "sql_to_json",
    "json_to_sql",
    "validate_filter",
]
