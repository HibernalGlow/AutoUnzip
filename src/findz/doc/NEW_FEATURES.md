# findz 新功能文档

## 嵌套压缩包搜索

使用 `--nested` 或 `-N` 选项搜索包含其他压缩包的外层压缩包。

### 示例

```bash
# 搜索包含嵌套压缩包的压缩包
python -m findz --nested /path/to/search

# 带详细信息
python -m findz --nested --long /path/to/search
```

### 工作原理

该功能会扫描所有文件(包括压缩包内部的文件),如果发现压缩包内部还包含其他压缩包文件,则将该外层压缩包路径记录下来。

例如:
- `outer.zip` 包含 `inner.zip` → 输出: `outer.zip`
- `archive.tar.gz` 包含 `data.zip` → 输出: `archive.tar.gz`

## 保存结果到文件

### 直接保存 (`--output` 或 `-o`)

```bash
# 保存搜索结果到文件
python -m findz "ext = 'py'" -o results.txt

# CSV格式保存
python -m findz "ext = 'py'" --csv -o results.csv
```

### 询问保存 (`--ask-save`)

搜索完成后提示用户是否保存结果:

```bash
python -m findz "ext = 'py'" --ask-save
```

程序会在显示结果后询问:
```
是否保存结果到文件? [y/n]:
```

如果选择 yes,会要求输入文件名(提供默认值)。

## 错误处理

### 继续错误 (默认行为)

默认情况下,遇到错误会继续搜索并在最后显示错误摘要:

```bash
python -m findz "ext = 'py'" /path1 /path2
```

即使 `/path1` 不存在,程序也会继续搜索 `/path2`,最后显示:
```
警告: 遇到 1 个错误
  - /path1: 系统找不到指定的文件
```

### 遇错停止 (`--stop-on-error`)

如果希望遇到第一个错误就停止:

```bash
python -m findz "ext = 'py'" /path1 --stop-on-error
```

## 组合使用

所有功能可以组合使用:

```bash
# 搜索嵌套压缩包并保存结果
python -m findz --nested /path/to/search -o nested_archives.txt

# 搜索文件,遇错继续,完成后询问是否保存
python -m findz "ext = 'py'" /path1 /path2 --ask-save

# 搜索所有压缩包,保存到文件,遇错停止
python -m findz "ext = 'zip' OR ext = 'tar'" /path --stop-on-error -o archives.txt
```

## 性能提示

对于大型目录:

1. **禁用压缩包扫描** (如果不需要): `--no-archive` 或 `-n`
2. **使用缓存** (自动启用): 第二次搜索会快很多
3. **并行处理** (自动启用): 使用多核心加速搜索

示例:
```bash
# 快速搜索(不扫描压缩包内部)
python -m findz "ext = 'py'" --no-archive /large/directory

# 并行搜索多个路径
python -m findz "size > 1M" /path1 /path2 /path3
```

## 错误排查

### 缓存问题

如果遇到缓存相关警告,可以清除缓存:

```bash
# Windows
Remove-Item -Recurse -Force $env:USERPROFILE\.findz_cache

# Linux/Mac
rm -rf ~/.findz_cache
```

### 编码问题

findz 会自动处理各种字符编码。如果在控制台看到乱码,结果文件中的内容仍然是正确的。

### 权限错误

遇到权限错误时会显示警告但继续搜索(除非使用 `--stop-on-error`)。
