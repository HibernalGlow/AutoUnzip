#!/usr/bin/env python3
"""
ugrep 命令行选项演示脚本

功能：
- 逐项显示常用 ugrep 选项及中文解释（来源：你提供的 help 文本片段）
- 为每个选项给出一个安全的示例命令（基于 repo 下 scripts/demo_data）
- 支持 --execute 开关实际运行可安全运行的示例并展示输出（使用 rich 彩色面板）

用法：
    python scripts/ugrep_options_demo.py [--execute]

注意：运行示例需本机安装 ugrep；脚本默认只打印示例，不执行。使用 --execute 才会调用子进程执行命令并显示输出。
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.markdown import Markdown
except Exception:
    Console = None  # type: ignore

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / 'demo_data'

# 精选选项列表：每项包含 'opt', 'zh'（中文解释简要）, 'example'（示例命令数组）, 'safe'（是否自动可执行）
OPTIONS: List[Dict[str, object]] = [
    { 'opt': '-A NUM, --after-context=NUM',
      'zh': '输出匹配行后面的 NUM 行作为上下文（尾部上下文）。',
      'example': ['ugrep','-n','-A','2','-r','-i','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-a, --text',
      'zh': '将二进制文件作为文本处理（可能输出垃圾字符）。',
      'example': ['ugrep','-a','-n','255', str(DEMO)],
      'safe': False  # 可能输出二进制垃圾，保守地不自动执行
    },
    { 'opt': "--all, -@",
      'zh': '搜索所有文件（取消先前的文件/目录限制），可与后续限制组合使用。',
      'example': ['ugrep','-@','-n','avif', str(DEMO)],
      'safe': False
    },
    { 'opt': '--and [-e] PATTERN',
      'zh': '追加必须匹配的 PATTERN（与其它 -e 作为 OR 的组合）。',
      'example': ['ugrep','-n','--and','-e','avif','-e','AVIF', str(DEMO)],
      'safe': True
    },
    { 'opt': '--andnot [-e] PATTERN',
      'zh': '组合 --and 与 --not，用于复杂筛选。',
      'example': ['ugrep','-n','--andnot','-e','binary', str(DEMO)],
      'safe': False
    },
    { 'opt': '-B NUM, --before-context=NUM',
      'zh': '输出匹配行前面的 NUM 行作为上下文（前部上下文）。',
      'example': ['ugrep','-n','-B','1','-r','Hello', str(DEMO)],
      'safe': True
    },
    { 'opt': '-b, --byte-offset',
      'zh': '在匹配行前显示匹配的字节偏移。',
      'example': ['ugrep','-b','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': "--binary-files=TYPE",
      'zh': "控制二进制文件如何处理（binary/text/hex/with-hex/...）。",
      'example': ['ugrep','--binary-files=text','-n','-r','255', str(DEMO)],
      'safe': False
    },
    { 'opt': '--bool, -%',
      'zh': '布尔查询（AND/OR/NOT 组合）。',
      'example': ['ugrep','-n','--bool','A|B C|D', str(DEMO)],
      'safe': False
    },
    { 'opt': '-C NUM, --context=NUM',
      'zh': '输出匹配行前后各 NUM 行作为上下文。',
      'example': ['ugrep','-n','-C','2','-r','Hello', str(DEMO)],
      'safe': True
    },
    { 'opt': '-c, --count',
      'zh': '仅输出符合条件的行数或匹配计数。',
      'example': ['ugrep','-c','-r','--include=*.txt','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '--color[=WHEN]',
      'zh': '在终端为匹配文本上色（always/auto/never）。',
      'example': ['ugrep','--color=always','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '--colors=COLORS',
      'zh': '指定各类元素的颜色规则（如 ms=, fn=, ln=）。',
      'example': ['ugrep','--colors=ms=+r,fn=g','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '--format=FORMAT',
      'zh': '使用格式化输出字段（%f 文件名, %n 行号 等）。',
      'example': ['ugrep','--format=%f:%n:%O%~','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-d ACTION, --directories=ACTION',
      'zh': '指定目录作为输入时的处理（skip/read/recurse）。',
      'example': ['ugrep','-d','recurse','-n','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-e PATTERN, --regexp=PATTERN',
      'zh': '指定一个 PATTERN；可重复使用多次。',
      'example': ['ugrep','-n','-e','avif','-e','Hello', str(DEMO)],
      'safe': True
    },
    { 'opt': '-F, --fixed-strings',
      'zh': '把模式作为固定字符串集合匹配（类似 fgrep）。',
      'example': ['ugrep','-F','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-f FILE, --file=FILE',
      'zh': '从文件读取模式列表（每行一个）。',
      'example': ['ugrep','-f', str(DEMO / 'patterns.txt'), '-n', str(DEMO)],
      'safe': False
    },
    { 'opt': '-g GLOBS, --glob=GLOBS',
      'zh': '仅搜索匹配 glob 的文件（等同于 --include）。',
      'example': ['ugrep','-n','-g','*.txt','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-H, --with-filename',
      'zh': '始终显示文件名（多文件搜索默认开启）。',
      'example': ['ugrep','-H','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-h, --no-filename',
      'zh': '不显示文件名（单文件或 stdin 常用）。',
      'example': ['ugrep','-h','-n', str(DEMO / 'file1.txt')],
      'safe': True
    },
    { 'opt': '-I, --ignore-binary',
      'zh': '忽略二进制文件中的匹配（相当于 --binary-files=without-match）。',
      'example': ['ugrep','-I','-n','-r','255', str(DEMO)],
      'safe': True
    },
    { 'opt': '-i, --ignore-case',
      'zh': '忽略大小写的匹配。',
      'example': ['ugrep','-i','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '--include=GLOB',
      'zh': '只搜索匹配 GLOB 的文件名。',
      'example': ['ugrep','--include=*.txt','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-l, --files-with-matches',
      'zh': '仅列出包含匹配的文件名。',
      'example': ['ugrep','-l','-r','-i','--include=*.txt','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-L, --files-without-match',
      'zh': '仅列出不包含匹配的文件名。',
      'example': ['ugrep','-L','-r','--include=*.txt','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-n, --line-number',
      'zh': '在匹配行前显示行号。',
      'example': ['ugrep','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-o, --only-matching',
      'zh': '仅输出匹配到的文本部分。',
      'example': ['ugrep','-o','-r','-i','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-P, --perl-regexp',
      'zh': '使用 PCRE2 (Perl 风格正则)。',
      'example': ['ugrep','-P','-n','-r','\b(avif|AVIF)\b', str(DEMO)],
      'safe': True
    },
    { 'opt': '-r, -R, --recursive',
      'zh': '递归搜索目录（-R 同时跟随符号链接）。',
      'example': ['ugrep','-r','-n','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-s, --no-messages',
      'zh': '静默模式：忽略不可读文件的错误信息。',
      'example': ['ugrep','-s','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-U, --ascii, --binary',
      'zh': '按字节匹配（禁用 Unicode），用于精确字节匹配。',
      'example': ['ugrep','-U','-n','-r','\xFF', str(DEMO)],
      'safe': False
    },
    { 'opt': '-v, --invert-match',
      'zh': '反向匹配，输出不匹配的行。',
      'example': ['ugrep','-v','-n','-r','avif', str(DEMO)],
      'safe': True
    },
    { 'opt': '-z, --decompress',
      'zh': '搜索压缩文件和归档（zip/7z/tar 等）。',
      'example': ['ugrep','-z','-n','--include=*.zip','avif', str(DEMO)],
      'safe': True
    },
]

# 一些选项的示例需要准备，比如 -f 的 patterns.txt，我们在不执行时只展示示例。


def run_and_render(cmd: List[str], execute: bool, title: Optional[str] = None):
    """如果 execute=True 则执行命令并用 rich 输出结果，否则只打印命令示例。"""
    if Console is None:
        print('\n' + ('='*40))
        if title:
            print(title)
        print('Command:', ' '.join(cmd))
        if execute:
            try:
                subprocess.run(cmd, check=False)
            except FileNotFoundError:
                print('<命令未找到，跳过>')
        return

    console = Console()
    header = title or (' '.join(cmd))
    console.rule(header)
    console.print('[dim]示例命令：[/dim]')
    console.print(Panel(' '.join(cmd), title='命令', style='cyan'))
    if execute:
        if shutil.which(cmd[0]) is None:
            console.print(Panel(f"命令未安装：{cmd[0]}，跳过执行。", style='yellow'))
            return
        # 执行并捕获输出
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = proc.communicate()
            out_txt = out.decode('utf-8', errors='replace').rstrip() or '<no output>'
            err_txt = err.decode('utf-8', errors='replace').rstrip()
            console.print(Panel(out_txt, title='stdout', style='white'))
            if err_txt:
                console.print(Panel(err_txt, title='stderr', style='red'))
        except Exception as e:
            console.print(Panel(str(e), title='执行异常', style='red'))


def main():
    p = argparse.ArgumentParser(description='演示 ugrep 命令行选项（含中文解释）')
    p.add_argument('--execute', action='store_true', help='实际执行示例命令（默认只展示）')
    args = p.parse_args()

    if Console is None:
        print('注意：rich 未安装，输出为纯文本。建议安装 rich: pip install rich')

    # 表头
    if Console is not None:
        Console().print(Markdown('# ugrep 选项演示（中文说明）'))

    for entry in OPTIONS:
        opt = entry['opt']
        zh = entry['zh']
        example = entry['example']
        safe = entry.get('safe', False)

        if Console is not None:
            Console().print(Panel(f"{zh}", title=opt, style='magenta'))
        else:
            print('\n' + ('-'*40))
            print(opt)
            print(zh)

        # 当用户请求执行，并且该示例标记为 safe 时才执行
        if args.execute and safe:
            run_and_render([str(x) for x in example], execute=True, title=f"示例：{opt}")
        else:
            # 仅展示示例命令，不执行
            run_and_render([str(x) for x in example], execute=False, title=f"示例（未执行）：{opt}")

    if Console is not None:
        Console().print('\n[green]演示结束。若需执行全部示例请使用 --execute，并确保已安装 ugrep。[/green]')
    else:
        print('\n演示结束。若需执行全部示例请使用 --execute，并确保已安装 ugrep。')


if __name__ == '__main__':
    main()
