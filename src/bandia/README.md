# Bandia - 批量解压/压缩工具

使用 Bandizip (bz.exe) 进行批量解压和压缩操作。

## 功能

- **解压 (extract)**: 批量解压 `.zip .7z .rar .tar .gz .bz2 .xz` 格式
- **压缩 (compress)**: 批量压缩目录到压缩包
- **重压缩 (repack)**: 根据路径映射恢复原始压缩包
- 支持剪贴板/参数/交互式输入
- 支持解压/压缩后删除源文件（可选移入回收站）
- 支持进度回调（用于 GUI/WebSocket 集成）
- 支持并行处理提升性能
- 支持 Ctrl+C 优雅中断

## 安装

```bash
pip install typer rich pyperclip send2trash loguru
```

## CLI 使用

### 解压

```bash
# 从剪贴板解压（默认行为）
bandia extract

# 解压指定文件
bandia extract path/to/archive.zip path/to/another.7z

# 从剪贴板读取路径
bandia extract --clipboard

# 并行解压
bandia extract -P --workers 4

# 保留源文件（不删除）
bandia extract --keep

# 输出 JSON 格式结果（含路径映射）
bandia extract --json
```

### 压缩

```bash
# 压缩目录
bandia compress folder1 folder2

# 指定输出目录
bandia compress folder1 --output /path/to/output

# 保留源目录（不删除）
bandia compress folder1 --keep

# 使用 7z 格式
bandia compress folder1 --format 7z
```

### 重压缩（恢复压缩）

```bash
# 从文件读取映射
bandia repack mappings.json

# 从剪贴板读取映射
bandia repack --clipboard

# 保留源目录
bandia repack --clipboard --keep
```

映射 JSON 格式：

```json
{
  "mappings": [
    {"archive_path": "/path/to/archive.zip", "extracted_path": "/path/to/folder"},
    ...
  ]
}
```

## API 使用

```python
from bandia import extract_batch, compress_batch, PathMapping, ProgressCallback

# 解压
result = extract_batch(
    paths=[Path("archive.zip")],
    delete=True,
    use_trash=True,
    parallel=True
)

print(f"成功: {result.extracted}, 失败: {result.failed}")
for r in result.results:
    if r.success:
        print(f"{r.path} -> {r.output_path}")

# 压缩（根据映射恢复）
mappings = [
    PathMapping(archive_path="/path/to/archive.zip", extracted_path="/path/to/folder")
]
result = compress_batch(
    mappings=mappings,
    delete_source=True
)

# 使用进度回调
callback = ProgressCallback(
    on_progress=lambda p, msg, f: print(f"{p}%: {msg}"),
    on_log=lambda msg: print(msg),
    throttle_interval=0.1
)

result = extract_batch(paths=[...], callback=callback)
```

## 模块结构

```
bandia/
├── __init__.py    # 导出核心函数供 API 使用
├── cli.py         # Typer CLI 入口 (子命令: extract, compress, repack)
├── core.py        # 核心业务逻辑
├── types.py       # 数据类定义
├── utils.py       # 工具函数
└── main.py        # 旧入口点 (已弃用)
```

## 导出的 API

```python
# 核心函数
from bandia import (
    extract_single,    # 解压单个文件
    extract_batch,     # 批量解压
    compress_single,   # 压缩单个目录
    compress_batch,    # 批量压缩
    get_output_path,   # 计算解压输出路径
)

# 类型
from bandia import (
    ExtractResult,
    BatchExtractResult,
    CompressResult,
    BatchCompressResult,
    PathMapping,
)

# 工具
from bandia import (
    ProgressCallback,
    find_bz_executable,
    parse_text_paths,
    filter_archives,
)
```

## 依赖

- **Bandizip**: 需要安装 Bandizip 并确保 `bz.exe` 在 PATH 中或设置 `BANDIZIP_PATH` 环境变量
- **Python**: >= 3.10
- **依赖包**: typer, rich, pyperclip, send2trash, loguru
