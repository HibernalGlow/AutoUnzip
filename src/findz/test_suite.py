"""Test script to verify findz installation and basic functionality."""

import sys
from pathlib import Path

# Add parent directory to path for testing
sys.path.insert(0, str(Path(__file__).parent))

from findz import create_filter
from findz.find.find import FileInfo
from datetime import datetime

def test_basic_filters():
    """Test basic filter functionality."""
    print("🧪 Testing findz filters...\n")
    
    # Create test files
    test_files = [
        FileInfo(
            name="small.txt",
            path="./small.txt",
            mod_time=datetime(2024, 10, 8, 10, 0, 0),
            size=512,
            file_type="file",
        ),
        FileInfo(
            name="large.zip",
            path="./large.zip",
            mod_time=datetime(2024, 10, 1, 12, 0, 0),
            size=10_485_760,  # 10MB
            file_type="file",
        ),
        FileInfo(
            name="test.py",
            path="./test.py",
            mod_time=datetime(2024, 10, 8, 15, 30, 0),
            size=2048,
            file_type="file",
        ),
        FileInfo(
            name="docs",
            path="./docs",
            mod_time=datetime(2024, 10, 5, 9, 0, 0),
            size=4096,
            file_type="dir",
        ),
    ]
    
    # Test cases
    test_cases = [
        ("size < 1K", ["small.txt"]),
        ("size > 1M", ["large.zip"]),
        ("ext = 'py'", ["test.py"]),
        ("type = 'dir'", ["docs"]),
        ("date = '2024-10-08'", ["small.txt", "test.py"]),
        ("name like 'test%'", ["test.py"]),
        ("size between 1K and 10K", ["test.py"]),
    ]
    
    passed = 0
    failed = 0
    
    for filter_str, expected_names in test_cases:
        try:
            filter_expr = create_filter(filter_str)
            matched = []
            
            for file in test_files:
                matches, error = filter_expr.test(file.context())
                if error:
                    print(f"  ❌ Error in filter '{filter_str}': {error}")
                    failed += 1
                    break
                elif matches:
                    matched.append(file.name)
            else:
                if matched == expected_names:
                    print(f"  ✅ '{filter_str}' -> {matched}")
                    passed += 1
                else:
                    print(f"  ❌ '{filter_str}'")
                    print(f"     Expected: {expected_names}")
                    print(f"     Got:      {matched}")
                    failed += 1
        except Exception as e:
            print(f"  ❌ Exception in filter '{filter_str}': {e}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0


def test_cli_help():
    """Test CLI help display."""
    print("\n🔧 Testing CLI...")
    try:
        from findz.cli import app
        print("  ✅ CLI module loaded successfully")
        return True
    except Exception as e:
        print(f"  ❌ Failed to load CLI: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("findz - Test Suite")
    print("=" * 50 + "\n")
    
    results = []
    
    # Test filters
    results.append(("Filter Tests", test_basic_filters()))
    
    # Test CLI
    results.append(("CLI Tests", test_cli_help()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
