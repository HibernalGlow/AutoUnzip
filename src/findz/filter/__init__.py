"""Filter module for findz - implements SQL-like WHERE clause filtering."""

from .filter import create_filter, FilterExpression
from .value import Value, number_value, text_value, bool_value
from .json_filter import (
    parse_json_filter,
    ast_to_json,
    condition,
    and_group,
    or_group,
    not_group,
    PRESET_FILTERS,
    get_preset,
    list_presets,
)
from .unified import (
    FilterMode,
    create_unified_filter,
    sql_to_json,
    json_to_sql,
    validate_filter,
    detect_filter_mode,
)

__all__ = [
    # 原有导出
    "create_filter",
    "FilterExpression",
    "Value",
    "number_value",
    "text_value",
    "bool_value",
    # JSON 过滤器
    "parse_json_filter",
    "ast_to_json",
    "condition",
    "and_group",
    "or_group",
    "not_group",
    "PRESET_FILTERS",
    "get_preset",
    "list_presets",
    # 统一接口
    "FilterMode",
    "create_unified_filter",
    "sql_to_json",
    "json_to_sql",
    "validate_filter",
    "detect_filter_mode",
]
