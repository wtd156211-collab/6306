"""结果文本渲染与 web/data.json 载荷组装。"""

from __future__ import annotations

import json
import os

from .engine import preference_entries

__all__ = ["render_result", "build_web_payload", "write_web_data"]


def render_result(result) -> str:
    """按 README 第 4 节格式渲染 stdout 文本（LF 换行，末尾一个换行）。"""
    lines = ["[配对]"]
    lines.extend(f"{a}-{b}" for a, b in result.pairs)
    lines.append("[落空-甲]")
    lines.extend(result.unmatched_a)
    lines.append("[落空-乙]")
    lines.extend(result.unmatched_b)
    return "\n".join(lines) + "\n"


def build_web_payload(case_name, case, result, blocking):
    """组装 web/data.json 的载荷，键一个都不能少。"""
    return {
        "case": case_name,
        "prefs_a": preference_entries(case.rank_a, case.ids_a),
        "prefs_b": preference_entries(case.rank_b, case.ids_b),
        "pairs": [{"a": a, "b": b} for a, b in result.pairs],
        "unmatched_a": list(result.unmatched_a),
        "unmatched_b": list(result.unmatched_b),
        "stats": {
            "matched": len(result.pairs),
            "proposals": result.proposals,
            "blocking": blocking,
        },
    }


def write_web_data(payload, web_dir):
    """把载荷写到 ``web_dir/data.json``，返回写出的路径。"""
    os.makedirs(web_dir, exist_ok=True)
    path = os.path.join(web_dir, "data.json")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path
