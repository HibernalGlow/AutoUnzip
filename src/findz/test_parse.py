"""Quick test of filter parsing."""
from findz.filter.lang import parse_filter
from findz.filter.filter import create_filter

# Test parsing
try:
    ast = parse_filter('ext = "py"')
    print(f"AST: {ast}")
    print("✅ Parsing successful")
except Exception as e:
    print(f"❌ Parsing failed: {e}")
    import traceback
    traceback.print_exc()

# Test filter creation
try:
    filter_expr = create_filter('ext = "py"')
    print("✅ Filter creation successful")
except Exception as e:
    print(f"❌ Filter creation failed: {e}")
    import traceback
    traceback.print_exc()
