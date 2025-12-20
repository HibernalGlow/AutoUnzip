"""SQL-like WHERE clause parser using pyparsing."""

import re
from typing import Any, Callable, Optional, Union
from pyparsing import (
    CaselessKeyword,
    Forward,
    Group,
    Literal,
    OneOrMore,
    Optional as Opt,
    ParseException,
    ParseResults,
    Regex,
    Suppress,
    Word,
    alphanums,
    alphas,
    delimitedList,
    infixNotation,
    opAssoc,
    pyparsing_common,
)

from .size import parse_size
from .value import Value, bool_value, number_value, text_value


class ASTNode:
    """Base class for AST nodes."""
    pass


class LiteralValue(ASTNode):
    """Represents a literal value in the expression."""
    
    def __init__(self, value: Any):
        self.value = value
    
    def __repr__(self):
        return f"LiteralValue({self.value!r})"


class SymbolRef(ASTNode):
    """Represents a symbol reference (variable name)."""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
    
    def __repr__(self):
        return f"SymbolRef({self.symbol!r})"


class BinaryOp(ASTNode):
    """Represents a binary operation."""
    
    def __init__(self, op: str, left: ASTNode, right: ASTNode):
        self.op = op
        self.left = left
        self.right = right
    
    def __repr__(self):
        return f"BinaryOp({self.op!r}, {self.left!r}, {self.right!r})"


class UnaryOp(ASTNode):
    """Represents a unary operation (NOT)."""
    
    def __init__(self, op: str, operand: ASTNode):
        self.op = op
        self.operand = operand
    
    def __repr__(self):
        return f"UnaryOp({self.op!r}, {self.operand!r})"


class LikeOp(ASTNode):
    """Represents LIKE/ILIKE/RLIKE operation."""
    
    def __init__(self, op: str, left: ASTNode, right: ASTNode, negated: bool = False):
        self.op = op
        self.left = left
        self.right = right
        self.negated = negated
        self.regex_cache: Optional[re.Pattern] = None
    
    def __repr__(self):
        neg = "NOT " if self.negated else ""
        return f"LikeOp({neg}{self.op!r}, {self.left!r}, {self.right!r})"


class BetweenOp(ASTNode):
    """Represents BETWEEN operation."""
    
    def __init__(self, expr: ASTNode, start: ASTNode, end: ASTNode, negated: bool = False):
        self.expr = expr
        self.start = start
        self.end = end
        self.negated = negated
    
    def __repr__(self):
        neg = "NOT " if self.negated else ""
        return f"BetweenOp({neg}{self.expr!r}, {self.start!r}, {self.end!r})"


class InOp(ASTNode):
    """Represents IN operation."""
    
    def __init__(self, expr: ASTNode, values: list, negated: bool = False):
        self.expr = expr
        self.values = values
        self.negated = negated
    
    def __repr__(self):
        neg = "NOT " if self.negated else ""
        return f"InOp({neg}{self.expr!r}, {self.values!r})"


def _parse_size_token(s, loc, toks):
    """Parse a size token like '10M' or '1G'."""
    return LiteralValue(parse_size(toks[0]))


def _parse_number(s, loc, toks):
    """Parse a number."""
    return LiteralValue(int(float(toks[0])))


def _parse_string(s, loc, toks):
    """Parse a string literal."""
    return LiteralValue(str(toks[0]))


def _parse_bool(s, loc, toks):
    """Parse a boolean literal."""
    return LiteralValue(toks[0].upper() == "TRUE")


def _parse_symbol(s, loc, toks):
    """Parse a symbol reference."""
    return SymbolRef(toks[0])


def _make_binary_op(tokens):
    """Create binary operation from infix notation."""
    # infixNotation 返回的 tokens 是嵌套的 ParseResults
    # 例如: [[left, 'AND', right]] 或 [[left, 'OR', right]]
    toks = tokens[0] if len(tokens) == 1 else tokens
    
    if len(toks) == 1:
        # 只有一个元素，直接返回
        return toks[0]
    elif len(toks) == 3:
        # 简单二元操作: left op right
        return BinaryOp(toks[1], toks[0], toks[2])
    else:
        # 多个操作 (left op1 mid op2 right ...)
        # 从左到右结合
        result = toks[0]
        for i in range(1, len(toks), 2):
            op = toks[i]
            right = toks[i + 1]
            result = BinaryOp(op, result, right)
        return result


def _make_like_op(tokens):
    """Create LIKE/ILIKE/RLIKE operation."""
    # tokens is a flat list: [left, 'LIKE'/'NOT', ...] or [left, 'NOT', 'LIKE', ...]
    left = tokens[0]
    negated = False
    idx = 1
    
    # Check for NOT keyword (it's a string)
    if len(tokens) > idx and isinstance(tokens[idx], str) and tokens[idx].upper() == "NOT":
        negated = True
        idx += 1
    
    # Get the operator keyword (LIKE, ILIKE, RLIKE)
    op = tokens[idx] if isinstance(tokens[idx], str) else str(tokens[idx])
    op = op.upper()
    right = tokens[idx + 1]
    
    return LikeOp(op, left, right, negated)


def _make_between_op(tokens):
    """Create BETWEEN operation."""
    # tokens is a flat list: [expr, 'BETWEEN'/'NOT', ...]
    expr = tokens[0]
    negated = False
    idx = 1
    
    # Check for NOT keyword
    if len(tokens) > idx and isinstance(tokens[idx], str) and tokens[idx].upper() == "NOT":
        negated = True
        idx += 1
    
    # Skip "BETWEEN" keyword
    idx += 1
    start = tokens[idx]
    # Skip "AND" keyword  
    idx += 2
    end = tokens[idx]
    
    return BetweenOp(expr, start, end, negated)


def _make_in_op(tokens):
    """Create IN operation."""
    # tokens 结构 (括号已被 Suppress): [expr, (NOT)?, 'IN', Group([values...])]
    toks = list(tokens)
    
    expr = toks[0]
    negated = False
    idx = 1
    
    # Check for NOT keyword
    if len(toks) > idx and isinstance(toks[idx], str) and toks[idx].upper() == "NOT":
        negated = True
        idx += 1
    
    # Skip "IN" keyword
    idx += 1
    
    # Extract values from the Group
    values = []
    values_group = toks[idx]
    
    # 处理 Group 或 ParseResults
    if isinstance(values_group, (list, ParseResults)):
        for v in values_group:
            if isinstance(v, ASTNode):
                values.append(v)
            elif isinstance(v, str):
                values.append(LiteralValue(v))
            else:
                values.append(LiteralValue(v))
    elif isinstance(values_group, ASTNode):
        values.append(values_group)
    
    return InOp(expr, values, negated)


# Define the grammar
def create_parser():
    """Create and return the SQL WHERE clause parser."""
    
    # Keywords (case-insensitive)
    AND = CaselessKeyword("AND")
    OR = CaselessKeyword("OR")
    NOT = CaselessKeyword("NOT")
    LIKE = CaselessKeyword("LIKE")
    ILIKE = CaselessKeyword("ILIKE")
    RLIKE = CaselessKeyword("RLIKE")
    BETWEEN = CaselessKeyword("BETWEEN")
    IN = CaselessKeyword("IN")
    TRUE = CaselessKeyword("TRUE")
    FALSE = CaselessKeyword("FALSE")
    
    # Operators
    EQ = Literal("=")
    NE = Literal("!=") | Literal("<>")
    LE = Literal("<=")
    GE = Literal(">=")
    LT = Literal("<")
    GT = Literal(">")
    
    # Literals
    size_literal = Regex(r"\d+\.?\d*[BKMGTbkmgt]").setParseAction(_parse_size_token)
    number_literal = pyparsing_common.number().setParseAction(_parse_number)
    
    # String literal (quoted strings)
    string_literal = (
        Regex(r"'[^']*'|\"[^\"]*\"")
        .setParseAction(lambda t: LiteralValue(t[0][1:-1]))  # Remove quotes
    )
    
    bool_literal = (TRUE | FALSE).setParseAction(_parse_bool)
    
    # Identifier (symbol reference)
    identifier = Word(alphas + "_", alphanums + "_").setParseAction(_parse_symbol)
    
    # Expression forward declaration
    expr = Forward()
    
    # Primary expression (literal or identifier or parenthesized expression)
    primary = (
        size_literal
        | bool_literal
        | number_literal
        | string_literal
        | identifier
        | ("(" + expr + ")").setParseAction(lambda t: t[1])
    )
    
    # Comparison operators
    comparison_op = EQ | NE | LE | GE | LT | GT
    
    # LIKE/ILIKE/RLIKE
    like_expr = (
        primary + Opt(NOT) + (LIKE | ILIKE | RLIKE) + primary
    ).setParseAction(_make_like_op)
    
    # BETWEEN
    between_expr = (
        primary + Opt(NOT) + BETWEEN + primary + AND + primary
    ).setParseAction(_make_between_op)
    
    # IN - 使用 Suppress 忽略括号
    in_expr = (
        primary + Opt(NOT) + IN + Suppress("(") + Group(delimitedList(primary)) + Suppress(")")
    ).setParseAction(_make_in_op)
    
    # Comparison
    comparison_expr = (primary + comparison_op + primary).setParseAction(_make_binary_op)
    
    # Combine all operands
    operand = like_expr | between_expr | in_expr | comparison_expr | primary
    
    # Build expression with precedence
    expr <<= infixNotation(
        operand,
        [
            (NOT, 1, opAssoc.RIGHT, lambda t: UnaryOp("NOT", t[0][1])),
            (AND, 2, opAssoc.LEFT, _make_binary_op),
            (OR, 2, opAssoc.LEFT, _make_binary_op),
        ],
    )
    
    return expr


# Create a global parser instance
_parser = create_parser()


def parse_filter(filter_string: str) -> ASTNode:
    """Parse a filter string and return an AST.
    
    Args:
        filter_string: SQL WHERE-like filter expression
    
    Returns:
        Root node of the abstract syntax tree
    
    Raises:
        ParseException: If the filter string is invalid
    """
    try:
        result = _parser.parseString(filter_string, parseAll=True)
        return result[0]
    except ParseException as e:
        raise ValueError(f"Invalid filter syntax: {e}")
