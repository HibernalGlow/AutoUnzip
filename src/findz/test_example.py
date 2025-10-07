"""Example usage of findz."""

from findz import create_filter
from findz.find.find import FileInfo
from datetime import datetime

# Create some test FileInfo objects
test_files = [
    FileInfo(
        name="test.txt",
        path="/home/user/test.txt",
        mod_time=datetime(2024, 1, 15, 10, 30, 0),
        size=1024,
        file_type="file",
    ),
    FileInfo(
        name="large.zip",
        path="/home/user/large.zip",
        mod_time=datetime(2024, 3, 20, 14, 45, 0),
        size=10_000_000,
        file_type="file",
    ),
    FileInfo(
        name="README.md",
        path="/home/user/docs/README.md",
        mod_time=datetime(2024, 10, 8, 9, 0, 0),
        size=2048,
        file_type="file",
    ),
]

# Test filters
filters = [
    'size < 10K',
    'size > 1M',
    'name like "%.txt"',
    'ext = "md"',
    'date > "2024-03-01"',
    'size between 1K and 100K',
]

print("Testing findz filters...\n")

for filter_str in filters:
    print(f"Filter: {filter_str}")
    try:
        filter_expr = create_filter(filter_str)
        for file in test_files:
            matches, error = filter_expr.test(file.context())
            if error:
                print(f"  Error testing {file.name}: {error}")
            elif matches:
                print(f"  ✓ {file.name} (size: {file.size}, date: {file.mod_time.date()})")
    except Exception as e:
        print(f"  Error creating filter: {e}")
    print()

print("\nAll tests completed!")
