# 实现说明（README.md 的补充材料）

本文件只描述工程组织与操作步骤，口径一律以根目录 `README.md` 为准。

## 入口与模块划分

- `main.py`：命令行入口。`python3 main.py <用例文件>` 打印结果到 stdout；
  加 `--web` 额外写出 `web/data.json`。格式错误退出码 2，提示走 stderr。
- `stablematch/parser.py`：用例文件解析与全部格式校验（段结构、标识、
  名次连续不降序、重复对象、跨侧重名、引用存在性），抛 `ParseError`。
  标识字符串全文件共享同一对象，名次小整数缓存，控制大规模内存。
- `stablematch/engine.py`：
  - `build_case`：把解析结果整理成引擎结构。`prefs_a` 只保留互相可接受
    的乙并按 (名次, 标识) 升序（即算法用严格序）；`rank_a`/`rank_b` 是
    全量名次索引，供 O(1) 比较；`full_*` 仅在 `--web` 时构建，供页面展示。
  - `solve`：甲侧主动的延迟接受主循环（迭代实现）。自由甲侧用最小堆，
    每轮取标识最小者；乙侧按严格序取舍。返回配对、两侧落空名单与
    `proposals`。
  - `verify_blocking`：弱稳定核验。枚举全部互相可接受对象对，用原始
    名次判定 better（严格更小才算，并列不算），未配对视同更优。
- `stablematch/report.py`：`to_text` 生成 stdout 文本；`to_json_payload`
  生成页面载荷；`write_json` 以流式方式写出 `web/data.json`（内容与
  载荷一致，但不一次性构建 200 万条目的字典，避免超出内存预算）。
- `web/index.html`：单文件原生 HTML + Canvas 页面，不引第三方库。
- `tests/test_engine.py`：unittest 测试。
- `bench.py`：性能基准脚本。

## 阻塞对自检步骤

引擎每次运行都会自检：`solve` 出结果后立即调用
`verify_blocking(case, result)`，把全部互相可接受对象对逐对套
「acc(a,b) ∧ better_a(b, M(a)) ∧ better_b(a, M(b))」三条判断：

1. 阻塞对数写进 `stats.blocking`（`--web` 时进入 `web/data.json`）；
2. 若阻塞对数非 0，stderr 打印警告并列出具体阻塞对（正确实现恒为 0）。

手动复验任一用例：

```bash
python3 - <<'EOF'
from stablematch import parse_case, build_case, solve, verify_blocking
text = open("samples/cases/04-ties.txt", encoding="utf-8").read()
case = build_case(*parse_case(text))
result = solve(case)
print(verify_blocking(case, result))  # 期望 []
EOF
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

覆盖：6 份样例逐行回归、提议次数、并列打破方向、单方意愿跳过、
落空名单、弱稳定核验（含「并列不算更偏好」「落空视同更优」的构造）、
重复运行确定性、JSON 载荷结构与流式写出一致性、各类格式错误的
退出码与行号提示。

## 性能基准

```bash
python3 bench.py          # 生成 1000 甲 × 1000 乙完整偏好表并计时
python3 bench.py --keep   # 保留生成的用例到 /tmp/bench-case.txt
```

实测（单核桌面 CPU）：引擎运行约 1.3s（预算 6s），峰值内存约
250 MB（预算 512 MB）；`--web` 模式约 1.5s / 273 MB。

## 页面运行

```bash
python3 main.py --web samples/cases/04-ties.txt   # 生成 web/data.json
cd web && python3 -m http.server 8000
# 浏览器访问 http://localhost:8000/
```

页面上的配对连线、落空名单、三个统计数字与顶部稳定性结论全部来自
`web/data.json`，页面不做任何重算。`file://` 直接打开会被浏览器
拦截 `fetch`，必须走 http 服务。
