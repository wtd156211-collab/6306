"""稳定匹配引擎入口。

用法：
    python3 main.py <用例文件>          按 README 第 4 节格式把结果打印到 stdout
    python3 main.py --web <用例文件>    同上，并额外写出 web/data.json
"""

from __future__ import annotations

import os
import sys

from stablematch import engine, parser, report

_USAGE = "用法: python3 main.py [--web] <用例文件>"


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    web = False
    if "--web" in args:
        args.remove("--web")
        web = True
    if len(args) != 1:
        return _fail(_USAGE)
    case_path = args[0]

    try:
        with open(case_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return _fail(f"无法读取用例文件 {case_path}：{exc.strerror or exc}")
    except UnicodeDecodeError as exc:
        return _fail(f"用例文件 {case_path} 不是合法的 UTF-8 文本：{exc}")

    try:
        case = parser.parse_case(text)
    except parser.CaseFormatError as exc:
        return _fail(f"格式错误：{exc}")

    result = engine.run(case)
    blocking = engine.count_blocking_pairs(case, result)

    sys.stdout.write(report.render_result(result))

    if web:
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        payload = report.build_web_payload(os.path.basename(case_path), case, result, blocking)
        out_path = report.write_web_data(payload, web_dir)
        print(f"已写出 {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
