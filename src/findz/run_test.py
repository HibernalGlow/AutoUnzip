"""运行测试并输出失败信息"""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_image_meta.py", "-v", "--tb=long"],
    capture_output=True,
    text=True,
    cwd="."
)

print("=== STDOUT ===")
print(result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout)
print("\n=== STDERR ===")
print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
print(f"\nExit code: {result.returncode}")
