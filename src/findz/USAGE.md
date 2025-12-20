# findz 使用手册

## 安装

```bash
cd PackU/AutoUnzip/src/findz
pip install -e .
```

## 基础搜索

```bash
# 搜索所有 py 文件
findz "ext = 'py'" /path

# 搜索大于 10MB 的文件
findz "size > 10M" /path

# 搜索今天修改的文件
findz "date = today" /path

# 组合条件
findz "ext = 'py' AND size < 100K" /path

# 模糊匹配
findz "name LIKE '%test%'" /path

# 正则匹配
findz "name RLIKE '^test_.*\.py$'" /path

# 多扩展名
findz "ext IN ('jpg', 'jpeg', 'png', 'gif')" /path
```

## 压缩包搜索

```bash
# 搜索压缩包内的文件
findz "ext = 'txt'" /path/to/archives

# 只列出包含匹配文件的压缩包（-A）
findz "ext = 'jpg'" /path -A

# 禁用压缩包搜索，加速（-n）
findz "ext = 'py'" /path -n

# 查找包含嵌套压缩包的外层压缩包（-N）
findz -N /path
```

## 输出格式

```bash
# 详细格式：日期 大小 路径（-l）
findz "ext = 'jpg'" /path -l

# CSV 格式
findz "ext = 'jpg'" /path --csv

# JSON 格式（方便 jq 处理）
findz "ext = 'jpg'" /path --json

# 保存到文件（-o）
findz "ext = 'jpg'" /path -o results.txt
```

## 分组统计（-G）

```bash
# 按压缩包分组
findz "ext = 'jpg'" /path -A -G archive

# 按扩展名分组
findz "1" /path -G ext

# 按目录分组
findz "1" /path -G dir
```

## 二次筛选（-R）

搜索后对结果进行过滤，支持的字段：
- `count` - 文件数量
- `avg_size` - 平均大小
- `total_size` - 总大小
- `name` - 分组名称

```bash
# 搜索 + 分组 + 筛选平均大小 > 2MB
findz "ext = 'avif'" /path -A -G archive -R "avg_size > 2M"

# 筛选文件数 > 10 的分组
findz "ext = 'jpg'" /path -A -G archive -R "count > 10"

# 筛选总大小 > 100MB
findz "ext = 'png'" /path -A -G archive -R "total_size > 100M"

# 组合条件
findz "ext = 'jpg'" /path -A -G archive -R "count > 5 AND avg_size > 1M"
```

## 排序（-S）

```bash
# 按平均大小降序（默认）
findz "ext = 'jpg'" /path -A -G archive -S avg_size

# 按数量升序
findz "ext = 'jpg'" /path -A -G archive -S count --asc

# 按名称排序
findz "ext = 'jpg'" /path -A -G archive -S name
```

## 实际案例

### 案例 1：找不包含 avif 的压缩包

思路：找包含 jpg/png/jxl 的压缩包（还没转换的）

```bash
findz "ext IN ('jpg', 'jpeg', 'png', 'jxl')" "E:\1Hub\EH\[02COS]" -A -o no_avif_archives.txt
```

### 案例 2：找包含 avif 且平均大小超过 2MB 的压缩包

```bash
findz "ext = 'avif'" "E:\1Hub\EH\[02COS]" -A -G archive -R "avg_size > 2M" -o avif_large.txt
```

### 案例 3：按扩展名统计，找文件数超过 100 的类型

```bash
findz "1" /path -G ext -R "count > 100"
```

### 案例 4：找大于 1GB 的压缩包

```bash
findz "ext IN ('zip', 'rar', '7z') AND size > 1G" /path -n
```

### 案例 5：JSON 输出配合 jq

```bash
# 输出 JSON
findz "ext = 'jpg'" /path --json > results.json

# 用 jq 筛选大于 1MB 的
findz "ext = 'jpg'" /path --json | jq '.[] | select(.size > 1000000)'

# PowerShell 处理
findz "ext = 'jpg'" /path --json | ConvertFrom-Json | Where-Object { $_.size -gt 1MB }
```

### 案例 6：从缓存二次筛选

搜索结果会自动缓存到 `~/.findz_cache/last_result.json`

```bash
# 先搜索
findz "ext = 'jpg'" /path -A

# 对缓存结果二次筛选（不提供路径）
findz -G archive -R "avg_size > 1M"
```

## 常用选项速查

| 选项 | 说明 |
|------|------|
| `-l` | 详细格式（日期、大小） |
| `-A` | 只输出压缩包路径 |
| `-N` | 查找嵌套压缩包 |
| `-n` | 禁用压缩包搜索 |
| `-G` | 分组统计（archive/ext/dir） |
| `-R` | 二次筛选表达式 |
| `-S` | 排序字段 |
| `-o` | 保存到文件 |
| `--json` | JSON 输出 |
| `--csv` | CSV 输出 |
| `-H` | 显示过滤语法帮助 |

## 过滤语法

### 字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `name` | 文件名 | `name = 'test.py'` |
| `path` | 完整路径 | `path LIKE '%/src/%'` |
| `ext` | 扩展名 | `ext = 'py'` |
| `size` | 文件大小 | `size > 1M` |
| `date` | 修改日期 | `date = '2025-01-01'` |
| `time` | 修改时间 | `time > '14:00:00'` |
| `type` | 类型 | `type = 'file'` |
| `archive` | 压缩包类型 | `archive = 'zip'` |
| `container` | 所在压缩包 | `container LIKE '%.zip'` |

### 操作符

- 比较：`=`, `!=`, `<>`, `<`, `>`, `<=`, `>=`
- 逻辑：`AND`, `OR`, `NOT`
- 模式：`LIKE`, `ILIKE`, `RLIKE`
- 范围：`BETWEEN`, `IN`
- 空值：`IS NULL`, `IS NOT NULL`

### 大小单位

`B`, `K`/`KB`, `M`/`MB`, `G`/`GB`, `T`/`TB`
