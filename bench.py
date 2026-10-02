#!/usr/bin/env python3
"""性能基准：生成 1000 甲 × 1000 乙的完整偏好表并计时。

用法：
    python3 bench.py            # 生成临时用例并跑引擎，报告耗时与内存
    python3 bench.py --keep     # 保留生成的用例文件到 /tmp/bench-case.txt
"""

import os
import random
import resource
import subprocess
import sys
import tempfile
import time

N = 1000


def generate(path, n=N, seed=20261003):
    rng = random.Random(seed)
    a_ids = [f"a{i:04d}" for i in range(1, n + 1)]
    b_ids = [f"b{i:04d}" for i in range(1, n + 1)]
    lines = ["# 基准用例：1000 甲 × 1000 乙，完整无并列", "[甲]"]
    for a in a_ids:
        order = b_ids[:]
        rng.shuffle(order)
        lines.append(f"{a}: " + ", ".join(f"{b}={i+1}" for i, b in enumerate(order)))
    lines.append("[乙]")
    for b in b_ids:
        order = a_ids[:]
        rng.shuffle(order)
        lines.append(f"{b}: " + ", ".join(f"{a}={i+1}" for i, a in enumerate(order)))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    keep = "--keep" in sys.argv
    path = "/tmp/bench-case.txt" if keep else None
    if path is None:
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="bench-")
        os.close(fd)
    try:
        t0 = time.perf_counter()
        generate(path)
        t1 = time.perf_counter()
        print(f"生成用例：{t1 - t0:.2f}s，{os.path.getsize(path) / 1e6:.1f} MB")

        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "main.py", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        elapsed = time.perf_counter() - t0
        peak_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        print(f"引擎运行：{elapsed:.2f}s（预算 6s），"
              f"峰值内存 {peak_kb / 1024:.0f} MB（预算 512 MB），"
              f"退出码 {proc.returncode}")
        if proc.stderr:
            print("stderr:", proc.stderr.strip())
        ok = proc.returncode == 0 and elapsed <= 6 and peak_kb <= 512 * 1024
        print("基准结论：", "通过" if ok else "未通过")
        return 0 if ok else 1
    finally:
        if not keep and os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    sys.exit(main())
