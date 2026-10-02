"""用例文件解析。

格式见仓库根目录 README.md 第 4 节。任何格式问题都抛
``ParseError``（消息带行号、中文），由入口转为退出码 2。
"""

import re

ID_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")

# 名次缓存：避免大规模用例下重复创建 int 对象。
_SMALL_INTS = tuple(int(i) for i in range(1001))


def _intern_rank(n):
    return _SMALL_INTS[n] if n <= 1000 else n


class ParseError(Exception):
    """用例文件格式错误。"""


def parse_case(text):
    """把用例文本解析成结构化原始数据。

    返回 ``(raw_a, raw_b)``：

    - ``raw_*`` 是 ``{标识: [(对方标识, 名次), ...]}``，顺序按文件
      出现顺序保留（引擎会按口径重新排序）。

    解析只做格式与引用合法性校验；「互相可接受」在引擎里处理。
    """
    lines = text.replace("\ufeff", "").splitlines()
    section = None  # None / "甲" / "乙"
    section_line = {"甲": None, "乙": None}
    seen_jia = False
    seen_yi = False
    raws = {"甲": {}, "乙": {}}
    ids = {"甲": set(), "乙": set()}
    # 标识规范化：同一标识在全文件共享同一个 str 对象，
    # 大规模用例下能省掉上百万份字符串副本。
    canon = {}
    # 每个标识的定义行号，供跨侧引用校验报错用。
    def_lines = {"甲": {}, "乙": {}}

    def intern(text_value):
        cached = canon.get(text_value)
        if cached is None:
            canon[text_value] = text_value
            return text_value
        return cached

    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            if line == "[甲]":
                if seen_jia:
                    raise ParseError(f"第 {lineno} 行：[甲] 段重复出现")
                seen_jia = True
                section = "甲"
                section_line["甲"] = lineno
                continue
            if line == "[乙]":
                if not seen_jia:
                    raise ParseError(f"第 {lineno} 行：[乙] 段出现在 [甲] 段之前")
                if seen_yi:
                    raise ParseError(f"第 {lineno} 行：[乙] 段重复出现")
                seen_yi = True
                section = "乙"
                section_line["乙"] = lineno
                continue
            raise ParseError(f"第 {lineno} 行：无法识别的段标题 {line}")

        if section is None:
            raise ParseError(f"第 {lineno} 行：数据行出现在段标题之前")

        head, sep, body = line.partition(":")
        if not sep:
            raise ParseError(f"第 {lineno} 行：数据行缺少英文冒号 ':'")
        ident = intern(head.strip())
        if not ID_RE.fullmatch(ident):
            raise ParseError(
                f"第 {lineno} 行：标识 {ident!r} 不合法"
                "（只允许 A-Za-z0-9_，长度 1~16）"
            )
        if ident in ids[section]:
            raise ParseError(f"第 {lineno} 行：标识 {ident} 在同侧重复定义")
        other_side = "乙" if section == "甲" else "甲"
        if ident in ids[other_side]:
            raise ParseError(f"第 {lineno} 行：标识 {ident} 与另一侧标识重名")

        entries = []
        if body.strip():
            prev_rank = 0
            targets = set()
            for chunk in body.split(","):
                piece = chunk.strip()
                target, eq, rank_text = piece.partition("=")
                if not eq:
                    raise ParseError(
                        f"第 {lineno} 行：偏好条目 {piece!r} 缺少 '名次' 部分"
                    )
                target = intern(target.strip())
                rank_text = rank_text.strip()
                if not ID_RE.fullmatch(target):
                    raise ParseError(
                        f"第 {lineno} 行：引用标识 {target!r} 不合法"
                        "（只允许 A-Za-z0-9_，长度 1~16）"
                    )
                if not rank_text.isdigit():
                    raise ParseError(
                        f"第 {lineno} 行：{target} 的名次 {rank_text!r} 不是正整数"
                    )
                rank = _intern_rank(int(rank_text))
                if rank < 1:
                    raise ParseError(
                        f"第 {lineno} 行：{target} 的名次必须从 1 开始"
                    )
                if rank < prev_rank:
                    raise ParseError(
                        f"第 {lineno} 行：名次必须按不降序书写"
                        f"（{rank} 出现在 {prev_rank} 之后）"
                    )
                if target in targets:
                    raise ParseError(
                        f"第 {lineno} 行：对象 {target} 在同一行重复出现"
                    )
                if target == ident:
                    raise ParseError(
                        f"第 {lineno} 行：标识 {ident} 不能把自己列为偏好对象"
                    )
                targets.add(target)
                entries.append((target, rank))
                prev_rank = rank
            uniq_sorted = sorted({rank for _, rank in entries})
            if uniq_sorted != list(range(1, len(uniq_sorted) + 1)):
                raise ParseError(
                    f"第 {lineno} 行：名次跳号（出现的名次为 "
                    f"{', '.join(str(r) for r in uniq_sorted)}，应从 1 起连续）"
                )

        ids[section].add(ident)
        raws[section][ident] = entries
        def_lines[section][ident] = lineno

    if not seen_jia:
        at = section_line["乙"] if seen_yi else 1
        raise ParseError(f"第 {at} 行：缺少 [甲] 段")
    if not seen_yi:
        at = section_line["甲"]
        raise ParseError(f"第 {at} 行：缺少 [乙] 段")

    # 跨侧引用：行里引用的对象必须在另一侧定义。
    for side, other in (("甲", "乙"), ("乙", "甲")):
        for ident, entries in raws[side].items():
            for target, _ in entries:
                if target not in raws[other]:
                    lineno = def_lines[side][ident]
                    raise ParseError(
                        f"第 {lineno} 行：{ident} 引用了未在 [{other}] 段"
                        f"定义的标识 {target}"
                    )

    return raws["甲"], raws["乙"]
