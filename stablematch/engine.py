"""延迟接受（Gale-Shapley）求解与弱稳定核验。

口径见仓库根目录 README.md 第 2、3 节：

- 甲侧主动（提议方）；
- 双方都列出对方才算互相可接受，单方意愿不参与匹配与核验；
- 严格序（名次小者优先；并列按标识升序）只用于算法过程；
- 稳定性核验只用原始名次，严格更小才算 better，并列不算更偏好。
"""

import heapq

def build_case(raw_a, raw_b, keep_full=False):
    """把解析结果整理成引擎数据结构。

    返回字典，含：

    - ``ids_a`` / ``ids_b``：标识升序序列；
    - ``prefs_a``：``{甲标识: [(乙标识, 名次), ...]}``，
      按 (名次, 标识) 升序，只保留互相可接受的乙；
    - ``rank_a`` / ``rank_b``：``{标识: {对方: 名次}}`` 名次索引，
      保留全量原始条目供 O(1) 比较（单边条目不会被算法与核验走到，
      保留它可以避免再复制 200 万个条目）；
    - ``full_a`` / ``full_b``：仅 ``keep_full`` 时存在，按
      (名次, 标识) 升序的全量原始条目（含单方意愿），供页面展示。

    全程复用 parser 产出的 ``(标识, 名次)`` 元组，不复制全量偏好。
    """
    rank_a = {a: dict(entries) for a, entries in raw_a.items()}
    rank_b = {b: dict(entries) for b, entries in raw_b.items()}

    prefs_a = {}
    for a, entries in raw_a.items():
        mutual = [e for e in entries if a in rank_b.get(e[0], ())]
        mutual.sort(key=lambda item: (item[1], item[0]))
        prefs_a[a] = mutual

    case = {
        "ids_a": sorted(raw_a),
        "ids_b": sorted(raw_b),
        "prefs_a": prefs_a,
        "rank_a": rank_a,
        "rank_b": rank_b,
    }
    if keep_full:
        case["full_a"] = {
            a: sorted(entries, key=lambda item: (item[1], item[0]))
            for a, entries in raw_a.items()
        }
        case["full_b"] = {
            b: sorted(entries, key=lambda item: (item[1], item[0]))
            for b, entries in raw_b.items()
        }
    return case


def solve(case):
    """甲侧主动的延迟接受主循环（迭代实现）。

    返回 ``{"pairs", "unmatched_a", "unmatched_b", "proposals"}``。
    每轮固定取尚未配对且游标没走完的甲侧中标示最小者；
    每对互相可接受对象最多提议一次。
    """
    prefs_a = case["prefs_a"]
    rank_b = case["rank_b"]

    cursor = {a: 0 for a in case["ids_a"]}
    matched_a = {}  # a -> b
    matched_b = {}  # b -> a
    # 自由甲侧的最小堆；初始所有人自由（无偏好者取不出时直接落空）。
    free = list(case["ids_a"])
    heapq.heapify(free)
    proposals = 0

    while free:
        a = heapq.heappop(free)
        if a in matched_a:
            continue  # 理论上不会出现，防御性检查
        order = prefs_a[a]
        pos = cursor[a]
        if pos >= len(order):
            continue  # 游标走完仍未配对：永久落空，不再入堆
        b, rank_a_to_b = order[pos]
        cursor[a] = pos + 1
        proposals += 1

        current = matched_b.get(b)
        if current is None:
            matched_a[a] = b
            matched_b[b] = a
            continue

        # 乙侧按严格序取舍：名次小者优先，并列按甲标识升序。
        rank_current = rank_b[b][current]
        rank_new = rank_b[b][a]
        if (rank_new, a) < (rank_current, current):
            del matched_a[current]
            heapq.heappush(free, current)
            matched_a[a] = b
            matched_b[b] = a
        else:
            # 被拒：若游标还没走完，重新排队继续提议。
            if cursor[a] < len(order):
                heapq.heappush(free, a)

    pairs = sorted(matched_a.items())
    unmatched_a = [a for a in case["ids_a"] if a not in matched_a]
    unmatched_b = [b for b in case["ids_b"] if b not in matched_b]
    return {
        "pairs": pairs,
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b,
        "proposals": proposals,
    }


def _better_a(case, a, b, partner):
    """a 是否更偏好 b 于 partner；partner 为 None 表示 a 未配对。

    核验只用原始名次：严格更小才算 better。
    未配对视同比任何可接受对象都更优（即 b 可接受即可）。
    """
    rank_of_b = case["rank_a"].get(a, {}).get(b)
    if rank_of_b is None:
        return False
    if partner is None:
        return True
    rank_of_partner = case["rank_a"].get(a, {}).get(partner)
    return rank_of_partner is not None and rank_of_b < rank_of_partner


def _better_b(case, b, a, partner):
    rank_of_a = case["rank_b"].get(b, {}).get(a)
    if rank_of_a is None:
        return False
    if partner is None:
        return True
    rank_of_partner = case["rank_b"].get(b, {}).get(partner)
    return rank_of_partner is not None and rank_of_a < rank_of_partner


def verify_blocking(case, result):
    """枚举全部互相可接受对象对，逐对核验弱稳定。

    阻塞对条件：acc(a,b) 且 a 未配对或严格更偏好 b 于现配对，
    且 b 未配对或严格更偏好 a 于现配对。返回阻塞对列表
    （``(a, b)``，按 a、b 升序）。
    """
    partner_a = dict(result["pairs"])
    partner_b = {b: a for a, b in result["pairs"]}
    blocking = []
    for a in case["ids_a"]:
        pa = partner_a.get(a)
        for b, _ in case["prefs_a"][a]:  # prefs_a[a] 只含互相可接受的 b
            if _better_a(case, a, b, pa) and _better_b(case, b, a, partner_b.get(b)):
                blocking.append((a, b))
    blocking.sort()
    return blocking
