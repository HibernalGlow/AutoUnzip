"""Filter expression evaluation."""

import re
from typing import Callable, Optional

from .lang import (
    ASTNode,
    BetweenOp,
    BinaryOp,
    InOp,
    LikeOp,
    LiteralValue,
    SymbolRef,
    UnaryOp,
    parse_filter,
)
from .value import Value


# Type alias for variable getter function
VariableGetter = Callable[[str], Optional[Value]]


class FilterExpression:
    """A compiled filter expression that can be tested against variables."""
    
    def __init__(self, ast: ASTNode):
        self.ast = ast
        # 检测是否是简单的 "1" 或 "true" 过滤器（匹配所有）
        self._is_match_all = self._check_match_all(ast)
    
    def _check_match_all(self, node: ASTNode) -> bool:
        """检查是否是匹配所有的过滤器"""
        if isinstance(node, LiteralValue):
            if isinstance(node.value, bool):
                return node.value
            elif isinstance(node.value, int):
                return node.value != 0
        return False
    
    def test(self, getter: VariableGetter) -> tuple[bool, Optional[Exception]]:
        """Test whether the variables match this filter.
        
        Args:
            getter: Function that returns Value for a given variable name
        
        Returns:
            Tuple of (matches, error). If error is not None, matches is False.
        """
        # 快速路径：匹配所有
        if self._is_match_all:
            return (True, None)
        
        try:
            result = self._eval(self.ast, getter)
            return (result.to_bool(), None)
        except Exception as e:
            return (False, e)
    
    def _eval(self, node: ASTNode, getter: VariableGetter) -> Value:
        """Evaluate an AST node and return a Value."""
        
        if isinstance(node, LiteralValue):
            # Return the literal value
            if isinstance(node.value, bool):
                return Value(boolean=node.value)
            elif isinstance(node.value, int):
                return Value(number=node.value)
            elif isinstance(node.value, str):
                return Value(text=node.value)
            else:
                raise ValueError(f"Unknown literal type: {type(node.value)}")
        
        elif isinstance(node, SymbolRef):
            # Look up the symbol value
            val = getter(node.symbol)
            if val is None:
                raise ValueError(f"Unknown symbol: {node.symbol}")
            return val
        
        elif isinstance(node, BinaryOp):
            return self._eval_binary_op(node, getter)
        
        elif isinstance(node, UnaryOp):
            return self._eval_unary_op(node, getter)
        
        elif isinstance(node, LikeOp):
            return self._eval_like_op(node, getter)
        
        elif isinstance(node, BetweenOp):
            return self._eval_between_op(node, getter)
        
        elif isinstance(node, InOp):
            return self._eval_in_op(node, getter)
        
        else:
            raise ValueError(f"Unknown node type: {type(node)}")
    
    def _eval_binary_op(self, node: BinaryOp, getter: VariableGetter) -> Value:
        """Evaluate a binary operation."""
        op = node.op.upper()
        
        # Logical operators
        if op == "AND":
            left = self._eval(node.left, getter)
            if not left.to_bool():
                return Value(boolean=False)
            right = self._eval(node.right, getter)
            return Value(boolean=right.to_bool())
        
        elif op == "OR":
            left = self._eval(node.left, getter)
            if left.to_bool():
                return Value(boolean=True)
            right = self._eval(node.right, getter)
            return Value(boolean=right.to_bool())
        
        # Comparison operators
        left = self._eval(node.left, getter)
        right = self._eval(node.right, getter)
        
        # Number comparison
        if left.number is not None and right.number is not None:
            l, r = left.number, right.number
            if op == "=":
                result = l == r
            elif op in ("!=", "<>"):
                result = l != r
            elif op == "<":
                result = l < r
            elif op == ">":
                result = l > r
            elif op == "<=":
                result = l <= r
            elif op == ">=":
                result = l >= r
            else:
                raise ValueError(f"Unknown operator: {op}")
            return Value(boolean=result)
        
        # Text comparison
        elif left.text is not None and right.text is not None:
            l, r = left.text, right.text
            if op == "=":
                result = l == r
            elif op in ("!=", "<>"):
                result = l != r
            elif op == "<":
                result = l < r
            elif op == ">":
                result = l > r
            elif op == "<=":
                result = l <= r
            elif op == ">=":
                result = l >= r
            else:
                raise ValueError(f"Unknown operator: {op}")
            return Value(boolean=result)
        
        # Boolean comparison
        elif left.boolean is not None and right.boolean is not None:
            l, r = left.boolean, right.boolean
            if op == "=":
                result = l == r
            elif op in ("!=", "<>"):
                result = l != r
            else:
                raise ValueError(f"Invalid operator for boolean: {op}")
            return Value(boolean=result)
        
        else:
            raise ValueError("Type mismatch in comparison")
    
    def _eval_unary_op(self, node: UnaryOp, getter: VariableGetter) -> Value:
        """Evaluate a unary operation (NOT)."""
        if node.op.upper() == "NOT":
            operand = self._eval(node.operand, getter)
            return Value(boolean=not operand.to_bool())
        else:
            raise ValueError(f"Unknown unary operator: {node.op}")
    
    def _eval_like_op(self, node: LikeOp, getter: VariableGetter) -> Value:
        """Evaluate a LIKE/ILIKE/RLIKE operation."""
        left = self._eval(node.left, getter)
        right = self._eval(node.right, getter)
        
        if left.text is None or right.text is None:
            raise ValueError("LIKE requires text operands")
        
        # Build regex if not cached
        if node.regex_cache is None:
            pattern = right.text
            
            if node.op == "RLIKE":
                # Use pattern directly as regex
                node.regex_cache = re.compile(pattern)
            else:
                # Convert SQL LIKE to regex
                # First, replace SQL wildcards with placeholders
                pattern = pattern.replace("%", "\x00")  # Placeholder for %
                pattern = pattern.replace("_", "\x01")  # Placeholder for _
                # Then escape regex special chars
                pattern = re.escape(pattern)
                # Finally, replace placeholders with regex equivalents
                pattern = pattern.replace("\x00", ".*")
                pattern = pattern.replace("\x01", ".")
                pattern = "^" + pattern + "$"
                
                flags = re.IGNORECASE if node.op == "ILIKE" else 0
                node.regex_cache = re.compile(pattern, flags)
        
        match = node.regex_cache.match(left.text) is not None
        
        if node.negated:
            match = not match
        
        return Value(boolean=match)
    
    def _eval_between_op(self, node: BetweenOp, getter: VariableGetter) -> Value:
        """Evaluate a BETWEEN operation."""
        expr = self._eval(node.expr, getter)
        start = self._eval(node.start, getter)
        end = self._eval(node.end, getter)
        
        # Number comparison
        if (
            expr.number is not None
            and start.number is not None
            and end.number is not None
        ):
            result = start.number <= expr.number <= end.number
        # Text comparison
        elif expr.text is not None and start.text is not None and end.text is not None:
            result = start.text <= expr.text <= end.text
        else:
            raise ValueError("Type mismatch in BETWEEN")
        
        if node.negated:
            result = not result
        
        return Value(boolean=result)
    
    def _eval_in_op(self, node: InOp, getter: VariableGetter) -> Value:
        """Evaluate an IN operation."""
        expr = self._eval(node.expr, getter)
        
        # 使用缓存的值集合加速查找
        if not hasattr(node, '_value_cache'):
            # 预计算所有值
            node._text_values = set()
            node._number_values = set()
            for val_node in node.values:
                if isinstance(val_node, LiteralValue):
                    if isinstance(val_node.value, str):
                        node._text_values.add(val_node.value)
                    elif isinstance(val_node.value, (int, float)):
                        node._number_values.add(val_node.value)
            node._value_cache = True
        
        # 快速路径：使用 set 查找
        if expr.text is not None and node._text_values:
            result = expr.text in node._text_values
        elif expr.number is not None and node._number_values:
            result = expr.number in node._number_values
        else:
            # 回退到逐个比较
            result = False
            for val_node in node.values:
                val = self._eval(val_node, getter)
                
                if expr.number is not None and val.number is not None:
                    if expr.number == val.number:
                        result = True
                        break
                elif expr.text is not None and val.text is not None:
                    if expr.text == val.text:
                        result = True
                        break
                elif expr.boolean is not None and val.boolean is not None:
                    if expr.boolean == val.boolean:
                        result = True
                        break
        
        if node.negated:
            result = not result
        
        return Value(boolean=result)


def create_filter(filter_string: str) -> FilterExpression:
    """Create a compiled filter expression from a filter string.
    
    Args:
        filter_string: SQL WHERE-like filter expression
    
    Returns:
        Compiled FilterExpression that can be tested
    
    Raises:
        ValueError: If the filter string is invalid
    """
    ast = parse_filter(filter_string)
    return FilterExpression(ast)
