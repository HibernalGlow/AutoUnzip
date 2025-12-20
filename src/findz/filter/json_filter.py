"""
JSON 配置格式的过滤器解析器
支持可视化构建器生成的 JSON 配置

JSON 配置格式示例:
{
    "op": "and",  // 逻辑运算符: and, or
    "conditions": [
        { "field": "size", "op": ">", "value": "10M" },
        { "field": "ext", "op": "in", "value": ["zip", "rar"] },
        {
            "op": "or",
            "conditions": [
                { "field": "date", "op": "=", "value": "today" },
                { "field": "date", "op": ">", "value": "2024-01-01" }
            ]
        }
    ]
}

简单条件格式:
{ "field": "size", "op": ">", "value": "10M" }

支持的运算符:
- 比较: =, !=, <>, <, >, <=, >=
- 模式: like, ilike, rlike
- 范围: between, in, not_in
- 逻辑: and, or, not
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

from .lang import (
    ASTNode,
    BetweenOp,
    BinaryOp,
    InOp,
    LikeOp,
    LiteralValue,
    SymbolRef,
    UnaryOp,
)
from .size import parse_size


class FilterOperator(str, Enum):
    """过滤器运算符"""
    # 比较运算符
    EQ = "="
    NE = "!="
    NE2 = "<>"
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    # 模式运算符
    LIKE = "like"
    ILIKE = "ilike"
    RLIKE = "rlike"
    NOT_LIKE = "not_like"
    NOT_ILIKE = "not_ilike"
    NOT_RLIKE = "not_rlike"
    # 范围运算符
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"
    IN = "in"
    NOT_IN = "not_in"
    # 逻辑运算符
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class JsonCondition:
    """单个条件"""
    field: str
    op: str
    value: Any
    # between 专用
    value_end: Optional[Any] = None


@dataclass
class JsonFilterGroup:
    """条件组"""
    op: str  # and, or
    conditions: List[Union['JsonFilterGroup', JsonCondition]]
    negated: bool = False


def parse_json_filter(config: Union[Dict, List, str]) -> ASTNode:
    """
    解析 JSON 配置为 AST
    
    Args:
        config: JSON 配置，可以是:
            - 字典: 单个条件或条件组
            - 列表: 条件数组（默认 AND 连接）
            - 字符串: JSON 字符串
    
    Returns:
        AST 节点
    
    Raises:
        ValueError: 配置格式错误
    """
    import json
    
    # 如果是字符串，先解析 JSON
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError as e:
            raise ValueError(f"无效的 JSON 格式: {e}")
    
    # 如果是列表，转换为 AND 组
    if isinstance(config, list):
        config = {"op": "and", "conditions": config}
    
    # 解析配置
    return _parse_node(config)


def _parse_node(node: Dict) -> ASTNode:
    """解析单个节点"""
    if not isinstance(node, dict):
        raise ValueError(f"期望字典，得到 {type(node)}")
    
    # 检查是条件组还是单个条件
    if "conditions" in node:
        return _parse_group(node)
    elif "field" in node:
        return _parse_condition(node)
    else:
        raise ValueError(f"无效的节点格式: {node}")


def _parse_group(group: Dict) -> ASTNode:
    """解析条件组"""
    op = group.get("op", "and").lower()
    conditions = group.get("conditions", [])
    negated = group.get("negated", False)
    
    if not conditions:
        # 空条件组，返回 true
        return LiteralValue(True)
    
    # 解析所有子条件
    parsed_conditions = [_parse_node(c) for c in conditions]
    
    # 用逻辑运算符连接
    if len(parsed_conditions) == 1:
        result = parsed_conditions[0]
    else:
        result = parsed_conditions[0]
        for cond in parsed_conditions[1:]:
            result = BinaryOp(op.upper(), result, cond)
    
    # 处理否定
    if negated:
        result = UnaryOp("NOT", result)
    
    return result


def _parse_condition(cond: Dict) -> ASTNode:
    """解析单个条件"""
    field = cond.get("field")
    op = cond.get("op", "=").lower()
    value = cond.get("value")
    
    if not field:
        raise ValueError("条件缺少 field 字段")
    
    # 创建字段引用
    field_ref = SymbolRef(field)
    
    # 解析值
    value_node = _parse_value(value, field)
    
    # 根据运算符类型创建节点
    if op in ("=", "!=", "<>", "<", ">", "<=", ">="):
        return BinaryOp(op if op != "<>" else "!=", field_ref, value_node)
    
    elif op in ("like", "ilike", "rlike"):
        return LikeOp(op.upper(), field_ref, value_node, negated=False)
    
    elif op in ("not_like", "not_ilike", "not_rlike"):
        actual_op = op.replace("not_", "").upper()
        return LikeOp(actual_op, field_ref, value_node, negated=True)
    
    elif op == "between":
        value_end = cond.get("value_end")
        if value_end is None:
            # 尝试从 value 数组获取
            if isinstance(value, list) and len(value) >= 2:
                value_node = _parse_value(value[0], field)
                end_node = _parse_value(value[1], field)
            else:
                raise ValueError("between 运算符需要 value_end 或 value 数组")
        else:
            end_node = _parse_value(value_end, field)
        return BetweenOp(field_ref, value_node, end_node, negated=False)
    
    elif op == "not_between":
        value_end = cond.get("value_end")
        if value_end is None:
            if isinstance(value, list) and len(value) >= 2:
                value_node = _parse_value(value[0], field)
                end_node = _parse_value(value[1], field)
            else:
                raise ValueError("not_between 运算符需要 value_end 或 value 数组")
        else:
            end_node = _parse_value(value_end, field)
        return BetweenOp(field_ref, value_node, end_node, negated=True)
    
    elif op == "in":
        if not isinstance(value, list):
            value = [value]
        value_nodes = [_parse_value(v, field) for v in value]
        return InOp(field_ref, value_nodes, negated=False)
    
    elif op == "not_in":
        if not isinstance(value, list):
            value = [value]
        value_nodes = [_parse_value(v, field) for v in value]
        return InOp(field_ref, value_nodes, negated=True)
    
    else:
        raise ValueError(f"未知的运算符: {op}")


def _parse_value(value: Any, field: str = "") -> ASTNode:
    """解析值为 AST 节点"""
    # 特殊值处理
    if isinstance(value, str):
        # 检查是否是大小值（如 10M, 1G）
        if field == "size" or (value and value[-1].upper() in "BKMGT" and value[:-1].replace(".", "").isdigit()):
            try:
                size_bytes = parse_size(value)
                return LiteralValue(size_bytes)
            except ValueError:
                pass
        
        # 检查是否是特殊符号（today, mo, tu 等）
        if value.lower() in ("today", "mo", "tu", "we", "th", "fr", "sa", "su"):
            return SymbolRef(value.lower())
        
        return LiteralValue(value)
    
    elif isinstance(value, bool):
        return LiteralValue(value)
    
    elif isinstance(value, (int, float)):
        return LiteralValue(int(value))
    
    elif value is None:
        return LiteralValue("")
    
    else:
        return LiteralValue(str(value))


def ast_to_json(ast: ASTNode) -> Dict:
    """
    将 AST 转换回 JSON 配置
    用于 SQL -> JSON 的转换
    
    Args:
        ast: AST 节点
    
    Returns:
        JSON 配置字典
    """
    if isinstance(ast, LiteralValue):
        return {"type": "literal", "value": ast.value}
    
    elif isinstance(ast, SymbolRef):
        return {"type": "symbol", "value": ast.symbol}
    
    elif isinstance(ast, BinaryOp):
        op = ast.op.lower()
        
        # 检查是否是逻辑运算符
        if op in ("and", "or"):
            # 收集所有同类型的条件
            conditions = _collect_binary_conditions(ast, op)
            return {
                "op": op,
                "conditions": conditions
            }
        else:
            # 比较运算符
            return {
                "field": _extract_field(ast.left),
                "op": ast.op,
                "value": _extract_value(ast.right)
            }
    
    elif isinstance(ast, UnaryOp):
        if ast.op.upper() == "NOT":
            inner = ast_to_json(ast.operand)
            if "conditions" in inner:
                inner["negated"] = True
            return inner
        return {"op": "not", "conditions": [ast_to_json(ast.operand)]}
    
    elif isinstance(ast, LikeOp):
        op = ast.op.lower()
        if ast.negated:
            op = f"not_{op}"
        return {
            "field": _extract_field(ast.left),
            "op": op,
            "value": _extract_value(ast.right)
        }
    
    elif isinstance(ast, BetweenOp):
        return {
            "field": _extract_field(ast.expr),
            "op": "not_between" if ast.negated else "between",
            "value": [_extract_value(ast.start), _extract_value(ast.end)]
        }
    
    elif isinstance(ast, InOp):
        return {
            "field": _extract_field(ast.expr),
            "op": "not_in" if ast.negated else "in",
            "value": [_extract_value(v) for v in ast.values]
        }
    
    else:
        raise ValueError(f"未知的 AST 节点类型: {type(ast)}")


def _collect_binary_conditions(ast: BinaryOp, op: str) -> List[Dict]:
    """收集二元运算的所有条件"""
    conditions = []
    
    # 递归收集左侧
    if isinstance(ast.left, BinaryOp) and ast.left.op.lower() == op:
        conditions.extend(_collect_binary_conditions(ast.left, op))
    else:
        conditions.append(ast_to_json(ast.left))
    
    # 递归收集右侧
    if isinstance(ast.right, BinaryOp) and ast.right.op.lower() == op:
        conditions.extend(_collect_binary_conditions(ast.right, op))
    else:
        conditions.append(ast_to_json(ast.right))
    
    return conditions


def _extract_field(node: ASTNode) -> str:
    """从 AST 节点提取字段名"""
    if isinstance(node, SymbolRef):
        return node.symbol
    raise ValueError(f"期望字段引用，得到 {type(node)}")


def _extract_value(node: ASTNode) -> Any:
    """从 AST 节点提取值"""
    if isinstance(node, LiteralValue):
        return node.value
    elif isinstance(node, SymbolRef):
        return node.symbol
    raise ValueError(f"期望字面值，得到 {type(node)}")


# ============ 便捷构建函数 ============

def condition(field: str, op: str, value: Any, value_end: Any = None) -> Dict:
    """创建单个条件"""
    result = {"field": field, "op": op, "value": value}
    if value_end is not None:
        result["value_end"] = value_end
    return result


def and_group(*conditions) -> Dict:
    """创建 AND 条件组"""
    return {"op": "and", "conditions": list(conditions)}


def or_group(*conditions) -> Dict:
    """创建 OR 条件组"""
    return {"op": "or", "conditions": list(conditions)}


def not_group(cond: Dict) -> Dict:
    """创建 NOT 条件"""
    if "conditions" in cond:
        return {**cond, "negated": True}
    return {"op": "and", "conditions": [cond], "negated": True}


# ============ 预设过滤器 ============

PRESET_FILTERS = {
    "all": {"op": "and", "conditions": []},
    "large_files": condition("size", ">", "100M"),
    "small_files": condition("size", "<", "1K"),
    "today": condition("date", "=", "today"),
    "this_week": condition("date", ">=", "mo"),
    "images": condition("ext", "in", ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"]),
    "videos": condition("ext", "in", ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm"]),
    "archives": condition("ext", "in", ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"]),
    "documents": condition("ext", "in", ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md"]),
    "code": condition("ext", "in", ["py", "js", "ts", "java", "c", "cpp", "h", "go", "rs", "rb"]),
    "in_archive": condition("archive", "!=", ""),
    "directories": condition("type", "=", "dir"),
    "files_only": condition("type", "=", "file"),
}


def get_preset(name: str) -> Optional[Dict]:
    """获取预设过滤器"""
    return PRESET_FILTERS.get(name)


def list_presets() -> List[str]:
    """列出所有预设名称"""
    return list(PRESET_FILTERS.keys())
