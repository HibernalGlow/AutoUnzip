from filter.filter import create_filter
from filter.lang import parse_filter

# Test LIKE pattern matching
ast = parse_filter("name LIKE 'test_%'")
print(f"AST: {ast}")
print(f"  Op: {ast.op}")
print(f"  Left: {ast.left}")
print(f"  Right: {ast.right}")
print(f"  Right value: {ast.right.value}")
print()

expr = create_filter("name LIKE 'test_%'")
print(f"Filter expression: {expr}")

# Test with a sample FileInfo object
class MockFileInfo:
    def __init__(self, name):
        self._name = name
    
    def context(self):
        """Return a getter function."""
        def getter(var):
            if var == "name":
                from filter.value import text_value
                return text_value(self._name)
            return None
        return getter

# Test cases
test_cases = [
    "test_parse.py",
    "test_example.py",
    "cli.py",
    "test.py",
]

for name in test_cases:
    fi = MockFileInfo(name)
    getter = fi.context()
    # Manually test the pattern
    import re
    pattern = "test_%"
    pattern = re.escape(pattern)
    print(f"  {name}:")
    print(f"    After escape: '{pattern}'")
    pattern = pattern.replace("\\%", ".*")
    print(f"    After %: '{pattern}'")
    pattern = pattern.replace("\\_", ".")
    print(f"    After _: '{pattern}'")
    pattern = "^" + pattern + "$"
    print(f"    Final: '{pattern}'")
    regex = re.compile(pattern)
    print(f"    Match: {regex.match(name)}")
    result = expr.test(getter)
    print(f"    Filter result: {result}")
