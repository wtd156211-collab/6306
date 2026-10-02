#!/usr/bin/env python3
"""稳定匹配引擎入口。

用法：
    python3 main.py <用例文件>          打印配对结果到 stdout
    python3 main.py --web <用例文件>    同上，并额外写出 web/data.json

格式错误：退出码 2，stderr 给出带行号的中文提示，stdout 不输出结果。
"""

import os
import sys

from stablematch import (
    ParseError,
    build_case,
    parse_case,
    solve,
    to_text,
    verify_blocking,
)
from stablematch.report import write_json

WEB_DATA_PATH = os.path.join("web", "data.json")


def main(argv):
    args = list(argv)
    web = False
    if "--web" in args:
        web = True
        args.remove("--web")
    if len(args) != 1:
        print(
            "用法：python3 main.py [--web] <用例文件>",
            file=sys.stderr,
        )
        return 2

    path = args[0]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"无法读取用例文件 {path}：{exc}", file=sys.stderr)
        return 2

    try:
        raw_a, raw_b = parse_case(text)
    except ParseError as exc:
        print(f"格式错误：{exc}", file=sys.stderr)
        return 2

    case = build_case(raw_a, raw_b, keep_full=web)
    del raw_a, raw_b
    result = solve(case)
    blocking = verify_blocking(case, result)
    if blocking:
        print(
            f"警告：核验发现 {len(blocking)} 个阻塞对：{blocking}",
            file=sys.stderr,
        )

    sys.stdout.write(to_text(result))

    if web:
        os.makedirs(os.path.dirname(WEB_DATA_PATH), exist_ok=True)
        with open(WEB_DATA_PATH, "w", encoding="utf-8") as fh:
            write_json(case, result, len(blocking), os.path.basename(path), fh)
        print(f"已写出 {WEB_DATA_PATH}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
