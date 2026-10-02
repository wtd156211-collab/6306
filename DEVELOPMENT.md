# 开发与运行说明

本文件是 README 第 7 节要求的补充材料，口径以 README 为准，本文不另立规则。

## 入口与模块划分

```text
main.py                  命令行入口：python3 main.py [--web] <用例文件>
stablematch/
  parser.py              用例文件解析与全部格式校验，产出名次索引与甲侧严格提议序
  engine.py              延迟接受主循环（迭代实现）+ 弱稳定阻塞对核验
  report.py              stdout 结果渲染、web/data.json 载荷组装与写出
web/index.html           单文件页面（原生 HTML + Canvas），只读 web/data.json
tests/test_engine.py     unittest 测试
benchmarks/bench_full_scale.py   满规模性能基准
```

- 甲侧主动提议；并列打破（名次升序、同名次按标识码点升序）只发生在
  `parser.py` 的提议序排序与 `engine.py` 的乙侧取舍里，核验路径只用原始名次。
- stdout 只放结果段；日志与错误走 stderr；格式错误退出码 2。

## 运行

```bash
python3 main.py samples/cases/04-ties.txt          # 结果打印到 stdout
python3 main.py --web samples/cases/04-ties.txt    # 同时写出 web/data.json
```

## 阻塞对自检

`engine.count_blocking_pairs(case, result)` 枚举全部互相可接受的对象对，
按「互相可接受 ∧ 甲严格更偏好 ∧ 乙严格更偏好」逐对判定（未配对视同更优，
并列不算更偏好），返回阻塞对数。`main.py` 每次运行都会执行该自检，
结果写入 `stats.blocking`（正确实现恒为 0）。测试里另有一组「人为反配
必须检出阻塞对」「并列解不得误判」的反向用例，防止核验本身退化成恒 0。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

覆盖：samples 逐行比对、提议数与说明一致、阻塞对 0、并列语义、单方意愿
过滤、落空规则、10 类非法输入的退出码与中文行号报错、重复运行字节一致、
`--web` 产物的键完整性与确定性。

## 性能基准

```bash
python3 benchmarks/bench_full_scale.py          # 1000×1000 满规模，计时+峰值内存
python3 benchmarks/bench_full_scale.py --keep   # 把生成的用例留在 /tmp 便于复跑
```

实测（本机）：解析+匹配+核验约 2 秒、峰值 RSS 约 264 MiB，低于
6 秒 / 512 MiB 预算。提议数上界为可接受对数，复杂度 O(甲 × 乙)。

## 页面

```bash
python3 main.py --web samples/cases/04-ties.txt   # 先生成 web/data.json
cd web && python3 -m http.server 8000             # 再开 http://localhost:8000/
```

页面展示：顶部三个统计数字（配对数 / 提议次数 / 阻塞对数）与稳定性结论、
Canvas 配对连线（左甲右乙，落空者排在分隔线以下）、两侧落空名单、
两侧全量偏好表（并列同名次蓝色标出）。所有数字与连线直接渲染
`data.json`，页面不做任何重算；`file://` 直接打开会被浏览器的
fetch 限制拦住，必须走 http 服务。
