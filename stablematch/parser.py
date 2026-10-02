"""用例文件解析。

读入文本后产出三样东西（只保留算法与核验需要的数据，不复制全量偏好）：

- ``proposal_lists``：甲侧每人按「名次升序、并列按标识码点升序」拉成的
  严格提议序，且已剔除乙侧没有回写的单方意愿条目；
- ``rank_a`` / ``rank_b``：``{标识: {对方标识: 名次}}`` 名次索引，供
  常数时间比较与弱稳定核验使用（核验只用原始名次，不用打破后的序）。
"""

from __future__ import annotations

import re

__all__ = ["CaseFormatError", "ParsedCase", "parse_case"]

_ID_RE = re.compile(r"[A-Za-z0-9_]{1,16}\Z")
_RANK_RE = re.compile(r"[0-9]+\Z")
_SECTION_A = "[甲]"
_SECTION_B = "[乙]"


class CaseFormatError(Exception):
    """用例文件格式错误，消息里带行号的中文提示。"""


class ParsedCase:
    __slots__ = ("ids_a", "ids_b", "proposal_lists", "rank_a", "rank_b")

    def __init__(self, ids_a, ids_b, proposal_lists, rank_a, rank_b):
        self.ids_a = ids_a
        self.ids_b = ids_b
        self.proposal_lists = proposal_lists
        self.rank_a = rank_a
        self.rank_b = rank_b


def _fail(lineno: int, message: str) -> None:
    raise CaseFormatError(f"第 {lineno} 行：{message}")


def parse_case(text: str) -> ParsedCase:
    """解析用例文本，格式错误时抛出 :class:`CaseFormatError`。"""
    if text.startswith("﻿"):
        text = text[1:]

    # 单遍解析，直接建名次索引，不保留中间条目列表（满规模下省一半内存）。
    # ranks[side][标识] = {对方标识: 名次}；owner_lineno 记录定义行号供报错。
    ranks = {"A": {}, "B": {}}
    owner_lineno = {"A": {}, "B": {}}
    side = None
    seen_a = False
    seen_b = False

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == _SECTION_A or line == _SECTION_B:
            if line == _SECTION_A:
                if seen_a:
                    _fail(lineno, "[甲] 段重复出现")
                if seen_b:
                    _fail(lineno, "[甲] 段必须出现在 [乙] 段之前")
                seen_a = True
                side = "A"
            else:
                if seen_b:
                    _fail(lineno, "[乙] 段重复出现")
                if not seen_a:
                    _fail(lineno, "[乙] 段之前缺少 [甲] 段")
                seen_b = True
                side = "B"
            continue
        if line.startswith("["):
            _fail(lineno, f"无法识别的段标题 {line!r}，只接受 [甲] 与 [乙]")
        if side is None:
            _fail(lineno, "数据行出现在 [甲] 段之前")

        head, sep, tail = line.partition(":")
        if not sep:
            _fail(lineno, "数据行缺少冒号，应为「标识: 对方=名次, ...」")
        owner = head.strip()
        if not _ID_RE.fullmatch(owner):
            _fail(lineno, f"标识 {owner!r} 不合法（限 A-Za-z0-9_，长度 1~16）")
        side_ranks = ranks[side]
        if owner in side_ranks:
            _fail(lineno, f"标识 {owner!r} 重复定义（首次出现在第 {owner_lineno[side][owner]} 行）")

        items = {}
        tail = tail.strip()
        if tail:
            prev_rank = 0
            for token in tail.split(","):
                token = token.strip()
                target, eq, rank_text = token.partition("=")
                target = target.strip()
                rank_text = rank_text.strip()
                if not eq or not target or not rank_text:
                    _fail(lineno, f"条目 {token!r} 写法不对，应为「对方=名次」")
                if not _ID_RE.fullmatch(target):
                    _fail(lineno, f"标识 {target!r} 不合法（限 A-Za-z0-9_，长度 1~16）")
                if not _RANK_RE.fullmatch(rank_text):
                    _fail(lineno, f"名次 {rank_text!r} 不是正整数")
                rank = int(rank_text)
                if rank < 1:
                    _fail(lineno, f"名次 {rank} 不是正整数（从 1 开始）")
                if target in items:
                    _fail(lineno, f"同一行里对象 {target!r} 重复出现")
                if rank < prev_rank:
                    _fail(lineno, f"名次 {rank} 比前一项小，行内名次必须不降序")
                if rank > prev_rank and rank != prev_rank + 1:
                    _fail(lineno, f"名次从 {prev_rank} 跳到 {rank}，名次必须连续不跳号")
                items[target] = rank
                prev_rank = rank
        side_ranks[owner] = items
        owner_lineno[side][owner] = lineno

    if not seen_a:
        raise CaseFormatError("第 1 行：缺少 [甲] 段")
    if not seen_b:
        raise CaseFormatError("第 1 行：缺少 [乙] 段")

    ids_a = sorted(ranks["A"])
    ids_b = sorted(ranks["B"])
    set_a = set(ids_a)
    set_b = set(ids_b)

    dup = set_a & set_b
    if dup:
        name = sorted(dup)[0]
        later = max(owner_lineno["A"][name], owner_lineno["B"][name])
        _fail(later, f"标识 {name!r} 在甲、乙两侧重复定义")

    # 跨侧引用校验：行里引用的对象必须在另一侧定义。
    for owner in ids_a:
        for target in ranks["A"][owner]:
            if target not in set_b:
                _fail(owner_lineno["A"][owner], f"{owner} 引用了不存在的乙侧标识 {target!r}")
    for owner in ids_b:
        for target in ranks["B"][owner]:
            if target not in set_a:
                _fail(owner_lineno["B"][owner], f"{owner} 引用了不存在的甲侧标识 {target!r}")

    rank_a = ranks["A"]
    rank_b = ranks["B"]
    proposal_lists = {}
    for owner in ids_a:
        owner_ranks = rank_a[owner]
        # 只保留乙侧回写过 owner 的条目（互相可接受才参与匹配）。
        mutual = [t for t in owner_ranks if owner in rank_b[t]]
        # 提议序：名次升序、并列按标识码点升序（Python 字符串序即码点序）。
        mutual.sort(key=lambda t: (owner_ranks[t], t))
        proposal_lists[owner] = mutual

    return ParsedCase(ids_a, ids_b, proposal_lists, rank_a, rank_b)
