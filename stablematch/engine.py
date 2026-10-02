"""甲侧主动的延迟接受算法，以及弱稳定（阻塞对）核验。"""

from __future__ import annotations

import heapq

__all__ = ["MatchResult", "run", "count_blocking_pairs", "preference_entries"]


class MatchResult:
    __slots__ = ("pairs", "unmatched_a", "unmatched_b", "proposals")

    def __init__(self, pairs, unmatched_a, unmatched_b, proposals):
        # pairs：[(甲, 乙), ...]，按甲侧标识升序
        self.pairs = pairs
        self.unmatched_a = unmatched_a
        self.unmatched_b = unmatched_b
        self.proposals = proposals


def run(case) -> MatchResult:
    """延迟接受主循环（迭代实现）。

    每轮固定取「尚未配对且提议游标没走完」的甲侧中标示最小者。
    并列打破只在本函数内生效：甲的提议序在解析阶段已定死，
    乙侧取舍时用「名次严格更小；并列看标识升序」比较。
    """
    cursor = {a: 0 for a in case.ids_a}
    match_a = {}  # 甲 -> 乙
    match_b = {}  # 乙 -> 甲
    proposals = 0

    heap = list(case.ids_a)
    heapq.heapify(heap)
    pushed = set(case.ids_a)

    def push(a):
        if a not in pushed:
            pushed.add(a)
            heapq.heappush(heap, a)

    while heap:
        a = heapq.heappop(heap)
        pushed.discard(a)
        # 堆里可能残留已经配对上的甲（被回推后又立刻接受了别处），跳过。
        if a in match_a:
            continue
        i = cursor[a]
        proposal_order = case.proposal_lists[a]
        if i >= len(proposal_order):
            continue  # 偏好走完：a 永久落空
        b = proposal_order[i]
        cursor[a] = i + 1
        proposals += 1

        incumbent = match_b.get(b)
        if incumbent is None:
            match_b[b] = a
            match_a[a] = b
            continue

        # 乙侧取舍：名次严格更小才算更想要；并列时标识码点升序优先。
        ranks = case.rank_b[b]
        r_new = ranks[a]
        r_old = ranks[incumbent]
        if r_new < r_old or (r_new == r_old and a < incumbent):
            match_b[b] = a
            del match_a[incumbent]
            match_a[a] = b
            push(incumbent)
        else:
            push(a)  # 被拒，保持自由继续往下提议

    pairs = sorted(match_a.items())
    unmatched_a = [a for a in case.ids_a if a not in match_a]
    unmatched_b = [b for b in case.ids_b if b not in match_b]
    return MatchResult(pairs, unmatched_a, unmatched_b, proposals)


def count_blocking_pairs(case, result) -> int:
    """枚举全部互相可接受的对象对，按原始名次核验阻塞对数。

    阻塞对条件：互相可接受，且各自未配对或严格更偏好对方于当前对象。
    并列名次不算更偏好，这里不得使用算法里的打破序。
    """
    partner_a = dict(result.pairs)
    partner_b = {b: a for a, b in result.pairs}
    blocking = 0
    for a in case.ids_a:
        a_ranks = case.rank_a[a]
        cur_b = partner_a.get(a)
        cur_rank_a = None if cur_b is None else a_ranks[cur_b]
        for b, rank_a in a_ranks.items():
            rank_b = case.rank_b[b].get(a)
            if rank_b is None:
                continue  # 单方意愿，不参与稳定性判定
            if cur_b is not None and not (rank_a < cur_rank_a):
                continue
            cur_a = partner_b.get(b)
            if cur_a is not None and not (rank_b < case.rank_b[b][cur_a]):
                continue
            blocking += 1
    return blocking


def preference_entries(rank_index, side_ids):
    """把名次索引转成页面/输出用的全量偏好条目。

    每人一份，按（名次, 标识）升序，并列原样保留；空偏好的人给空列表。
    """
    out = {}
    for owner in side_ids:
        ranks = rank_index[owner]
        out[owner] = [
            {"id": target, "rank": ranks[target]}
            for target in sorted(ranks, key=lambda t: (ranks[t], t))
        ]
    return out
