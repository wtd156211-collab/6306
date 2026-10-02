"""满规模基准：单侧 1000 人、每人 1000 条目（两侧完整，约 100 万可接受对）。

用法（仓库根目录）：
    python3 benchmarks/bench_full_scale.py            # 生成临时用例并计时
    python3 benchmarks/bench_full_scale.py --keep     # 用例写到 /tmp 保留下来

偏好为确定性伪随机置换（LCG，无第三方库），同参数生成的文件字节一致。
"""

from __future__ import annotations

import argparse
import os
import resource
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stablematch import engine, parser  # noqa: E402

N = 1000


def permutation(seed, n):
    """确定性伪随机置换（Fisher–Yates，LCG 提供随机数）。"""
    state = seed
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        state = (state * 1103515245 + 12345) % (1 << 31)
        j = state % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def build_case_text(n=N):
    lines = ["# 满规模基准：两侧完整偏好，名次为确定性伪随机置换", "[甲]"]
    for i in range(n):
        order = permutation(20261002 + i, n)
        ranked = sorted(range(n), key=lambda b: order[b])
        lines.append("a%04d: " % i + ", ".join("b%04d=%d" % (b, k + 1) for k, b in enumerate(ranked)))
    lines.append("[乙]")
    for j in range(n):
        order = permutation(777001 + j, n)
        ranked = sorted(range(n), key=lambda a: order[a])
        lines.append("b%04d: " % j + ", ".join("a%04d=%d" % (a, k + 1) for k, a in enumerate(ranked)))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="把生成的用例写到 /tmp 保留")
    args = ap.parse_args()

    t0 = time.perf_counter()
    text = build_case_text()
    t_gen = time.perf_counter() - t0

    path = None
    if args.keep:
        path = "/tmp/bench_full_scale.txt"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    t0 = time.perf_counter()
    case = parser.parse_case(text)
    result = engine.run(case)
    blocking = engine.count_blocking_pairs(case, result)
    elapsed = time.perf_counter() - t0
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    print(f"用例规模：{N} 甲 × {N} 乙（两侧完整），生成耗时 {t_gen:.2f}s"
          + (f"，文件 {path}（{os.path.getsize(path) // 1024} KiB）" if path else ""))
    print(f"解析+匹配+核验 wall clock：{elapsed:.2f}s（预算 6s）")
    print(f"峰值 RSS：{peak_kb // 1024} MiB（预算 512 MiB）")
    print(f"配对 {len(result.pairs)} 对，提议 {result.proposals} 次，阻塞对 {blocking}")
    assert blocking == 0
    assert elapsed <= 6.0, "超出时间预算"
    assert peak_kb // 1024 <= 512, "超出内存预算"
    print("PASS")


if __name__ == "__main__":
    main()
