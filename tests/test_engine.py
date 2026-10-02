"""引擎与命令行的 unittest 测试。

运行：仓库根目录下 ``python3 -m unittest discover -s tests -v``
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stablematch import engine, parser, report  # noqa: E402

CASES_DIR = os.path.join(ROOT, "samples", "cases")
EXPECTED_DIR = os.path.join(ROOT, "samples", "expected")


def load_case(name):
    with open(os.path.join(CASES_DIR, name), encoding="utf-8") as fh:
        return parser.parse_case(fh.read())


def normalize(text):
    """README 的比对口径：忽略行尾空白与文末空行。"""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


class SampleAcceptanceTests(unittest.TestCase):
    """对 samples/cases 的验收 1、2：逐行一致、阻塞对 0、提议数与说明一致。"""

    EXPECTED_PROPOSALS = {
        "01-classic.txt": 6,
        "02-multiple.txt": 7,
        "03-incomplete.txt": 5,
        "04-ties.txt": 10,
        "05-imbalance-a.txt": 10,
        "06-imbalance-b.txt": 3,
    }

    def test_all_samples_match_expected_and_are_stable(self):
        for name in sorted(self.EXPECTED_PROPOSALS):
            with self.subTest(case=name):
                case = load_case(name)
                result = engine.run(case)
                blocking = engine.count_blocking_pairs(case, result)
                self.assertEqual(blocking, 0)
                self.assertEqual(result.proposals, self.EXPECTED_PROPOSALS[name])

                output = report.render_result(result)
                expected_path = os.path.join(
                    EXPECTED_DIR, name.replace(".txt", ".result.txt"))
                with open(expected_path, encoding="utf-8") as fh:
                    expected = fh.read()
                self.assertEqual(normalize(output), normalize(expected))

    def test_stats_blocking_is_independently_recomputed(self):
        # stats.blocking 与核验函数结果一致（正确实现恒为 0）。
        for name in self.EXPECTED_PROPOSALS:
            with self.subTest(case=name):
                case = load_case(name)
                result = engine.run(case)
                payload = report.build_web_payload(name, case, result,
                                                   engine.count_blocking_pairs(case, result))
                self.assertEqual(payload["stats"]["blocking"], 0)


class ParsingTests(unittest.TestCase):
    def test_ties_broken_by_id_for_proposal_order_only(self):
        case = load_case("04-ties.txt")
        # a1 的 b2 与 b4 并列第 1，严格提议序里标识码点升序：b2 先于 b4。
        self.assertEqual(case.proposal_lists["a1"], ["b2", "b4", "b1", "b3"])
        # 原始名次索引保留并列，不被打破序改写。
        self.assertEqual(case.rank_a["a1"]["b2"], 1)
        self.assertEqual(case.rank_a["a1"]["b4"], 1)

    def test_one_sided_wishes_are_filtered_from_proposals(self):
        text = (
            "[甲]\n"
            "a1: b1=1, b2=2\n"
            "[乙]\n"
            "b1: a1=1\n"
            "b2:\n"
        )
        case = parser.parse_case(text)
        # b2 没回写 a1：单方意愿，不进提议序；但原始名次索引保留供页面展示。
        self.assertEqual(case.proposal_lists["a1"], ["b1"])
        self.assertEqual(case.rank_a["a1"]["b2"], 2)
        result = engine.run(case)
        self.assertEqual(result.pairs, [("a1", "b1")])
        self.assertEqual(result.unmatched_b, ["b2"])
        self.assertEqual(engine.count_blocking_pairs(case, result), 0)

    def test_empty_rows_and_imbalance(self):
        case = load_case("03-incomplete.txt")
        self.assertEqual(case.proposal_lists["a4"], [])
        self.assertEqual(case.rank_b["b4"].get("a3"), 2)  # b4 只想要 a3，a3 没回写

    def test_crlf_and_bom_accepted(self):
        text = "[甲]\r\na1: b1=1\r\n[乙]\r\nb1: a1=1\r\n"
        case = parser.parse_case("﻿" + text)
        result = engine.run(case)
        self.assertEqual(result.pairs, [("a1", "b1")])


class StabilitySemanticsTests(unittest.TestCase):
    def test_tie_is_not_strict_preference_in_verification(self):
        # 04-ties 的第 3 组弱稳定解：把打破方向反过来才会得到它；
        # 若核验误用打破后的严格序，这组解会被误判为不稳定。
        case = load_case("04-ties.txt")
        alt = engine.MatchResult(
            pairs=[("a1", "b4"), ("a2", "b3"), ("a3", "b2"), ("a4", "b1")],
            unmatched_a=[], unmatched_b=[], proposals=-1)
        self.assertEqual(engine.count_blocking_pairs(case, alt), 0)

    def test_verification_flags_a_genuine_blocking_pair(self):
        text = (
            "[甲]\n"
            "a1: b1=1, b2=2\n"
            "a2: b2=1, b1=2\n"
            "[乙]\n"
            "b1: a1=1, a2=2\n"
            "b2: a1=1, a2=2\n"
        )
        case = parser.parse_case(text)
        # 人为反配：a1-b2、a2-b1；(a1,b1) 互相都最想要 → 1 个阻塞对。
        bad = engine.MatchResult(
            pairs=[("a1", "b2"), ("a2", "b1")],
            unmatched_a=[], unmatched_b=[], proposals=-1)
        self.assertEqual(engine.count_blocking_pairs(case, bad), 1)

    def test_unmatched_beats_every_acceptable_partner(self):
        text = (
            "[甲]\n"
            "a1: b1=1\n"
            "a2: b1=1\n"
            "[乙]\n"
            "b1: a2=1, a1=2\n"
        )
        case = parser.parse_case(text)
        result = engine.run(case)
        # a1 落空；a1 与 b1 互相可接受且 a1 未配对，但 b1 更偏好 a2，故不阻塞。
        self.assertEqual(result.pairs, [("a2", "b1")])
        self.assertEqual(result.unmatched_a, ["a1"])
        self.assertEqual(engine.count_blocking_pairs(case, result), 0)


class CliTests(unittest.TestCase):
    def run_cli(self, *cli_args):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"), *cli_args],
            capture_output=True, text=True, cwd=ROOT)

    def test_sample_stdout_byte_stable_across_runs(self):
        path = os.path.join(CASES_DIR, "04-ties.txt")
        first = self.run_cli(path)
        second = self.run_cli(path)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        # stdout 只放结果，日志走 stderr。
        self.assertEqual(first.stderr, "")

    def test_web_data_is_byte_deterministic_and_consistent_with_page(self):
        path = os.path.join(CASES_DIR, "01-classic.txt")
        first = self.run_cli("--web", path)
        self.assertEqual(first.returncode, 0)
        data_path = os.path.join(ROOT, "web", "data.json")
        with open(data_path, "rb") as fh:
            bytes1 = fh.read()
        second = self.run_cli("--web", path)
        self.assertEqual(second.returncode, 0)
        with open(data_path, "rb") as fh:
            bytes2 = fh.read()
        self.assertEqual(bytes1, bytes2)

        data = json.loads(bytes2)
        self.assertEqual(set(data),
                         {"case", "prefs_a", "prefs_b", "pairs",
                          "unmatched_a", "unmatched_b", "stats"})
        self.assertEqual(set(data["stats"]), {"matched", "proposals", "blocking"})
        self.assertEqual(data["stats"]["matched"], len(data["pairs"]))
        # 页面展示的偏好条目数与全量标识一致（含空偏好行）。
        self.assertEqual(len(data["prefs_a"]), 3)
        self.assertEqual(len(data["prefs_b"]), 3)

        # index.html 里出现的三项统计都从 JSON 字段读取，不写死数字。
        with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        for field in ("stat-matched", "stat-proposals", "stat-blocking"):
            self.assertIn(field, html)

    def test_invalid_inputs_exit_2_with_chinese_lineno(self):
        bad_cases = {
            "missing_section.txt": "[甲]\na1: b1=1\n",
            "wrong_order.txt": "[乙]\nb1: a1=1\n[甲]\na1: b1=1\n",
            "bad_rank_order.txt": "[甲]\na1: b1=2\n[乙]\nb1: a1=1\n",
            "rank_gap.txt": "[甲]\na1: b1=1, b2=3\n[乙]\nb1: a1=1\nb2: a1=1\n",
            "dup_target.txt": "[甲]\na1: b1=1, b1=2\n[乙]\nb1: a1=1\n",
            "dup_owner.txt": "[甲]\na1: b1=1\na1: b1=2\n[乙]\nb1: a1=1\n",
            "cross_dup_name.txt": "[甲]\nx: y=1\n[乙]\nx: y=1\ny: x=1\n",
            "dangling_ref.txt": "[甲]\na1: b9=1\n[乙]\nb1: a1=1\n",
            "bad_id.txt": "[甲]\na-1: b1=1\n[乙]\nb1: a-1=1\n",
            "rank_zero.txt": "[甲]\na1: b1=0\n[乙]\nb1: a1=1\n",
        }
        for name, content in bad_cases.items():
            with self.subTest(case=name):
                with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                                 encoding="utf-8", delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    proc = self.run_cli(tmp_path)
                    self.assertEqual(proc.returncode, 2, msg=proc.stderr)
                    self.assertEqual(proc.stdout, "")
                    self.assertIn("第", proc.stderr)
                    self.assertIn("行", proc.stderr)
                finally:
                    os.unlink(tmp_path)

    def test_missing_file_exit_2(self):
        proc = self.run_cli(os.path.join(ROOT, "no-such-case.txt"))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
