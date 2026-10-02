"""结果输出：stdout 文本与 web/data.json 载荷。"""

import json


def _quote(ident):
    # 标识按口径只含 A-Za-z0-9_，可直接包引号，无需转义。
    return '"' + ident + '"'


def to_text(result):
    """按 README 第 4 节格式生成 stdout 文本（LF 换行，末尾留一个换行）。"""
    lines = ["[配对]"]
    lines.extend(f"{a}-{b}" for a, b in result["pairs"])
    lines.append("[落空-甲]")
    lines.extend(result["unmatched_a"])
    lines.append("[落空-乙]")
    lines.extend(result["unmatched_b"])
    return "\n".join(lines) + "\n"


def to_json_payload(case, result, blocking_count, case_name):
    """生成 web/data.json 的载荷（键一个都不能少）。

    ``prefs_*`` 给全量条目（含单方意愿），按名次、标识升序，
    并列原样保留；``pairs`` 按甲侧标识升序。
    """
    return {
        "case": case_name,
        "prefs_a": {
            a: [{"id": b, "rank": r} for b, r in case["full_a"][a]]
            for a in case["ids_a"]
        },
        "prefs_b": {
            b: [{"id": a, "rank": r} for a, r in case["full_b"][b]]
            for b in case["ids_b"]
        },
        "pairs": [{"a": a, "b": b} for a, b in result["pairs"]],
        "unmatched_a": list(result["unmatched_a"]),
        "unmatched_b": list(result["unmatched_b"]),
        "stats": {
            "matched": len(result["pairs"]),
            "proposals": result["proposals"],
            "blocking": blocking_count,
        },
    }


def write_json(case, result, blocking_count, case_name, fh):
    """把 data.json 载荷流式写入文件对象。

    与 ``to_json_payload`` 内容一致，但不一次性构建整个字典——
    1000×1000 规模下载荷有 200 万个条目，整体构建会超出内存预算。
    """
    w = fh.write
    w('{\n  "case": ' + json.dumps(case_name, ensure_ascii=False) + ',\n')
    for key, full, ids in (
        ("prefs_a", case["full_a"], case["ids_a"]),
        ("prefs_b", case["full_b"], case["ids_b"]),
    ):
        w(f'  "{key}": {{')
        first = True
        for ident in ids:
            if not first:
                w(",")
            first = False
            w(_quote(ident) + ":[" + ",".join(
                f'{{"id":{_quote(target)},"rank":{rank}}}'
                for target, rank in full[ident]
            ) + "]")
        w("},\n")
    w('  "pairs": [' + ",".join(
        f'{{"a":{_quote(a)},"b":{_quote(b)}}}' for a, b in result["pairs"]
    ) + "],\n")
    w('  "unmatched_a": [' + ",".join(
        _quote(a) for a in result["unmatched_a"]
    ) + "],\n")
    w('  "unmatched_b": [' + ",".join(
        _quote(b) for b in result["unmatched_b"]
    ) + "],\n")
    w('  "stats": {'
      f'"matched": {len(result["pairs"])}, '
      f'"proposals": {result["proposals"]}, '
      f'"blocking": {blocking_count}'
      "}\n}\n")
