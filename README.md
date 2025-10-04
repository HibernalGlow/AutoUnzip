# AutoUnzip 工具集

AutoUnzip 是一个围绕压缩包处理构建的小工具集合，包含自动解压、批处理与搜索分析能力。

## 7grep (grepu) 归档搜索

`7grep` 命令结合 7-Zip 与 ugrep，帮助你在一系列压缩包中快速定位特定后缀的文件，并统计匹配数量。

### 依赖

- [7-Zip](https://www.7-zip.org/) (`7z`)
- [ugrep](https://ugrep.com/)

请确保以上可执行文件已添加到 `PATH`。

### 快速开始

```powershell
# 交互式运行，按回车即可采用配置的默认值
7grep

# 非交互示例
7grep --path D:\\Archives --archives zip rar --formats png jpg --non-interactive
```

程序会输出：

1. ugrep 检索到的匹配文件列表
2. 针对每个压缩包的匹配数量与总文件数（通过 7z 统计）

### 配置文件

`7grep` 会按照以下优先级加载配置：

1. `--config` 指定的文件
2. `GREPU_CONFIG` 环境变量
3. `~/.config/grepu/config.toml`
4. 内置默认配置

运行 `7grep --init-config` 可在 `~/.config/grepu/config.toml` 生成一份默认配置：

```toml
[defaults]
search_path = "."
archive_formats = ["zip", "rar", "7z"]
search_extensions = ["jpg", "png", "gif"]

[ugrep]
flags = ["-r", "-U", "-l", "-i"]
```

你可以根据需要修改路径、压缩包后缀以及要匹配的文件后缀。
