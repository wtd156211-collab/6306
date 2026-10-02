"""引擎与入口的 unittest 测试。

运行：python3 -m unittest discover -s tests -v
"""

import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stablematch import (
    ParseError,
    build_case,
    parse_case,
    solve,
    to_json_payload,
    to_text,
    verify_blocking,
    write_json,
)
import main as cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "samples", "cases")
EXPECTED = os.path.join(ROOT, "samples", "expected")


def run_engine(text):
    raw_a, raw_b = parse_case(text)
    case = build_case(raw_a, raw_b, keep_full=True)
    result = solve(case)
    blocking = verify_blocking(case, result)
    return case, result, blocking


def normalize(text):
    # README 的比对口径：忽略行尾空白与文末空行。
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


class SampleRegression(unittest.TestCase):
    def test_all_samples_match_expected(self):
        for name in sorted(os.listdir(CASES)):
            if not name.endswith(".txt"):
                continue
            with self.subTest(case=name):
                with open(os.path.join(CASES, name), encoding="utf-8") as fh:
                    text = fh.read()
                _, result, blocking = run_engine(text)
                with open(
                    os.path.join(EXPECTED, name[:-4] + ".result.txt"),
                    encoding="utf-8",
                ) as fh:
                    expected = fh.read()
                self.assertEqual(normalize(to_text(result)), normalize(expected))
                self.assertEqual(len(blocking), 0)

    def test_classic_proposals_are_six(self):
        with open(os.path.join(CASES, "01-classic.txt"), encoding="utf-8") as fh:
            _, result, _ = run_engine(fh.read())
        self.assertEqual(result["proposals"], 6)

    def test_ties_picks_a_optimal_outcome(self):
        with open(os.path.join(CASES, "04-ties.txt"), encoding="utf-8") as fh:
            _, result, blocking = run_engine(fh.read())
        self.assertEqual(
            result["pairs"],
            [("a1", "b4"), ("a2", "b2"), ("a3", "b1"), ("a4", "b3")],
        )
        self.assertEqual(blocking, [])

    def test_imbalance_lists(self):
        with open(os.path.join(CASES, "05-imbalance-a.txt"), encoding="utf-8") as fh:
            _, result, _ = run_engine(fh.read())
        self.assertEqual(result["unmatched_a"], ["a1", "a3", "a4", "a6"])
        self.assertEqual(result["unmatched_b"], [])
        with open(os.path.join(CASES, "06-imbalance-b.txt"), encoding="utf-8") as fh:
            _, result, _ = run_engine(fh.read())
        self.assertEqual(result["unmatched_a"], [])
        self.assertEqual(result["unmatched_b"], ["b3", "b4", "b5"])


class OneSidedAndTies(unittest.TestCase):
    def test_one_sided_willingness_skipped(self):
        # a 列了 b2 但 b2 没列 a：单方意愿，不匹配、不算阻塞对。
        text = (
            "[甲]\n"
            "a1: b1=1, b2=2\n"
            "[乙]\n"
            "b1: a1=1\n"
            "b2:\n"
        )
        _, result, blocking = run_engine(text)
        self.assertEqual(result["pairs"], [("a1", "b1")])
        self.assertEqual(result["unmatched_a"], [])
        self.assertEqual(result["unmatched_b"], ["b2"])
        self.assertEqual(blocking, [])
        self.assertEqual(result["proposals"], 1)

    def test_mutual_pair_still_works(self):
        text = (
            "[甲]\n"
            "a1: b2=1\n"
            "[乙]\n"
            "b1:\n"
            "b2: a1=1\n"
        )
        _, result, blocking = run_engine(text)
        self.assertEqual(result["pairs"], [("a1", "b2")])
        self.assertEqual(result["unmatched_b"], ["b1"])
        self.assertEqual(blocking, [])

    def test_tie_broken_by_id_in_proposal_and_choice(self):
        # a1、a2 都把 b1 并列第一；b1 严格序（名次相同按甲标识升序）取 a1。
        text = (
            "[甲]\n"
            "a1: b1=1\n"
            "a2: b1=1\n"
            "[乙]\n"
            "b1: a1=1, a2=1\n"
        )
        _, result, blocking = run_engine(text)
        self.assertEqual(result["pairs"], [("a1", "b1")])
        self.assertEqual(result["unmatched_a"], ["a2"])
        self.assertEqual(blocking, [])  # 并列不算更偏好，a2 不构成阻塞对

    def test_identical_rank_when_b_has_strict_pref(self):
        # a1、a2 对 b1 并列第一；b1 更偏好 a2（严格名次），a2 抢人成功。
        text = (
            "[甲]\n"
            "a1: b1=1\n"
            "a2: b1=1\n"
            "[乙]\n"
            "b1: a2=1, a1=2\n"
        )
        _, result, _ = run_engine(text)
        self.assertEqual(result["pairs"], [("a2", "b1")])
        self.assertEqual(result["unmatched_a"], ["a1"])


class StabilityChecks(unittest.TestCase):
    def test_tie_does_not_count_as_better(self):
        # b1 把 a1、a3 并列第一：a1 拿到 b1 后，a3 不算“更被偏好”。
        text = (
            "[甲]\n"
            "a1: b1=1, b2=2\n"
            "a2: b2=1\n"
            "a3: b1=1\n"
            "[乙]\n"
            "b1: a1=1, a3=1\n"
            "b2: a1=1, a2=2\n"
        )
        _, result, blocking = run_engine(text)
        self.assertEqual(blocking, [])
        # a2 被 b2 拒绝后 a1-b1 保持不变
        self.assertEqual(dict(result["pairs"]).get("a1"), "b1")

    def test_unmatched_is_worse_than_any_acceptable(self):
        # 落空者与可接受对象（对方也更想要他）构成阻塞对的构造：
        # 直接验证核验器能抓出“理论上的”阻塞情形——
        # 给一个人为结果（绕过引擎）核验。
        text = (
            "[甲]\n"
            "a1: b1=1\n"
            "a2: b1=1\n"
            "[乙]\n"
            "b1: a2=1, a1=2\n"
        )
        raw_a, raw_b = parse_case(text)
        case = build_case(raw_a, raw_b)
        fake_result = {
            "pairs": [("a1", "b1")],
            "unmatched_a": ["a2"],
            "unmatched_b": [],
            "proposals": 1,
        }
        blocking = verify_blocking(case, fake_result)
        # a2 落空且 b1 严格更偏好 a2 -> (a2,b1) 是阻塞对
        self.assertEqual(blocking, [("a2", "b1")])


class Determinism(unittest.TestCase):
    def test_repeated_runs_identical(self):
        outputs = set()
        payloads = set()
        for name in sorted(os.listdir(CASES)):
            if not name.endswith(".txt"):
                continue
            for _ in range(3):
                with open(os.path.join(CASES, name), encoding="utf-8") as fh:
                    text = fh.read()
                case, result, blocking = run_engine(text)
                outputs.add((name, to_text(result)))
                payloads.add(
                    (name, json.dumps(
                        to_json_payload(case, result, len(blocking), name),
                        ensure_ascii=False,
                        sort_keys=True,
                    ))
                )
        self.assertEqual(len(outputs), 6)
        self.assertEqual(len(payloads), 6)


class JsonPayload(unittest.TestCase):
    def test_payload_keys_and_ordering(self):
        with open(os.path.join(CASES, "04-ties.txt"), encoding="utf-8") as fh:
            case, result, blocking = run_engine(fh.read())
        payload = to_json_payload(case, result, len(blocking), "04-ties.txt")
        for key in ("case", "prefs_a", "prefs_b", "pairs",
                    "unmatched_a", "unmatched_b", "stats"):
            self.assertIn(key, payload)
        self.assertEqual(set(payload["stats"]), {"matched", "proposals", "blocking"})
        # prefs 按 (名次, 标识) 升序，并列保留
        a1 = payload["prefs_a"]["a1"]
        self.assertEqual(
            [(p["id"], p["rank"]) for p in a1],
            [("b2", 1), ("b4", 1), ("b1", 2), ("b3", 2)],
        )
        self.assertEqual(payload["pairs"], [
            {"a": "a1", "b": "b4"},
            {"a": "a2", "b": "b2"},
            {"a": "a3", "b": "b1"},
            {"a": "a4", "b": "b3"},
        ])

    def test_full_prefs_include_one_sided_entries(self):
        # 页面要显示全量原始偏好（含单方意愿）
        text = (
            "[甲]\n"
            "a1: b1=1, b2=2\n"
            "[乙]\n"
            "b1: a1=1\n"
            "b2:\n"
        )
        case, result, blocking = run_engine(text)
        payload = to_json_payload(case, result, len(blocking), "x.txt")
        self.assertEqual(
            [p["id"] for p in payload["prefs_a"]["a1"]], ["b1", "b2"]
        )

    def test_streaming_writer_matches_payload(self):
        with open(os.path.join(CASES, "03-incomplete.txt"), encoding="utf-8") as fh:
            case, result, blocking = run_engine(fh.read())
        payload = to_json_payload(case, result, len(blocking), "03-incomplete.txt")
        buf = io.StringIO()
        write_json(case, result, len(blocking), "03-incomplete.txt", buf)
        self.assertEqual(json.loads(buf.getvalue()), payload)


class ParseErrors(unittest.TestCase):
    BAD_CASES = [
        ("[乙]\nb1: a1=1\n[甲]\na1: b1=1\n", "段顺序"),
        ("[甲]\na1 b1=1\n[乙]\n", "缺冒号"),
        ("[甲]\na1: b1=0\n[乙]\nb1:\n", "名次从 1 开始"),
        ("[甲]\na1: b1=1, b2=1, b3=3\n[乙]\nb1:\nb2:\nb3:\n", "名次跳号"),
        ("[甲]\na1: b2=1, b1=2\n[乙]\nb1: a1=1\n", "引用不存在"),
        ("[甲]\na1: b1=2\n[乙]\nb1: a1=1\n", "名次乱序"),
        ("[甲]\na1: b1=1, b1=2\n[乙]\nb1:\n", "重复对象"),
        ("[甲]\na1:\n[乙]\na1:\n", "跨侧重名"),
        ("[甲]\na1: b1=1\na1: b1=2\n[乙]\nb1: a1=1\n", "同侧重名"),
        ("x1: y1=1\n[甲]\n[乙]\n", "数据行在段前"),
        ("[甲]\na1: b1=1\n", "缺乙段"),
        ("[乙]\nb1:\n", "缺甲段（乙先出现）"),
    ]

    def test_bad_inputs_raise_with_line_number(self):
        for text, label in self.BAD_CASES:
            with self.subTest(label=label):
                with self.assertRaises(ParseError) as ctx:
                    parse_case(text)
                self.assertIn("行", str(ctx.exception))

    def test_empty_preference_rows_are_legal(self):
        text = "[甲]\na1:\n[乙]\nb1:\n"
        raw_a, raw_b = parse_case(text)
        self.assertEqual(raw_a, {"a1": []})
        case, result, blocking = run_engine(text)
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["unmatched_a"], ["a1"])
        self.assertEqual(result["unmatched_b"], ["b1"])
        self.assertEqual(blocking, [])

    def test_crlf_and_comments(self):
        text = "# 注释\r\n[甲]\r\na1: b1=1\r\n[乙]\r\nb1: a1=1\r\n"
        _, result, blocking = run_engine(text)
        self.assertEqual(result["pairs"], [("a1", "b1")])
        self.assertEqual(blocking, [])


class CliExitCodes(unittest.TestCase):
    def _run_cli(self, text, web=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "case.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            web_path = os.path.join(tmp, "web", "data.json")
            data = None
            old_cwd = os.getcwd()
            old_out, old_err = sys.stdout, sys.stderr
            os.chdir(tmp)
            sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
            try:
                argv = ["--web", path] if web else [path]
                code = cli.main(argv)
                if os.path.exists(web_path):
                    with open(web_path, encoding="utf-8") as fh:
                        data = json.load(fh)
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                os.chdir(old_cwd)
            return code, data

    def test_bad_input_exit_2_no_stdout_result(self):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out_buf, err_buf
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            ) as fh:
                fh.write("[甲]\na1: b9=1\n[乙]\n")
                path = fh.name
            code = cli.main([path])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            os.unlink(path)
        self.assertEqual(code, 2)
        self.assertEqual(out_buf.getvalue(), "")
        self.assertIn("行", err_buf.getvalue())

    def test_web_flag_writes_data_json(self):
        code, data = self._run_cli(
            "[甲]\na1: b1=1\n[乙]\nb1: a1=1\n", web=True
        )
        self.assertEqual(code, 0)
        self.assertEqual(data["pairs"], [{"a": "a1", "b": "b1"}])
        self.assertEqual(data["stats"]["blocking"], 0)

    def test_missing_file_exit_2(self):
        err_buf = io.StringIO()
        old_err = sys.stderr
        sys.stderr = err_buf
        try:
            code = cli.main(["/nonexistent/definitely-not-here.txt"])
        finally:
            sys.stderr = old_err
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
