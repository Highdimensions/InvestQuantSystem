# Phase 7 架构设计补充：一致性、Fuzz 与 Benchmark

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 7 实施 |
| 相关文档 | [Phase 6 设计](./backtest-phase6-design.md)、[可观测性设计](./backtest-observability.md)、[测试策略](./backtest-testing-strategy.md) |
| 最后更新 | 2026-07-03 |

---

## 1. 一致性测试（C1-C6）

### 1.1 断言清单

| 编号 | 断言 | 目的 |
| --- | --- | --- |
| C1 | 相同输入 + 相同参数 → 相同 signal_id | replay vs replay 确定性 |
| C2 | 相同输入 → 相同 signal count | replay 完整性 |
| C3 | universe 切换前后状态隔离 | 多 universe 一致性 |
| C4 | market_rules 拦截失败立即终止 | 风险规则一致性 |
| C5 | T+1 结算后单券仓位不超权重上限 | 组合约束一致性 |
| C6 | Evaluation 信号 id 与 Signal 一一对应 | 评价链路一致性 |

### 1.2 测试目录

- `tests/consistency/test_replay_consistency.py` — C1-C3
- `tests/consistency/test_live_vs_replay.py` — C7-C8（live vs shadow）

---

## 2. 实时影子对账

### 2.1 对账模型

| 维度 | 说明 |
| --- | --- |
| 比较目标 | replay_signal_ids vs shadow_signal_ids |
| 比较字段 | signal_id、direction、reason_codes |
| 容忍窗口 | 时间戳差异 ≤ 1 bar |

### 2.2 测试场景

| 场景 | 期望 |
| --- | --- |
| 影子完全一致 | 0 missing/extra/mismatch |
| 影子遗漏 1 个 signal | missing_in_shadow = 1 |
| 影子方向错误 | direction_mismatches = 1 |
| 影子多出 1 个 signal | extra_in_shadow = 1 |

### 2.3 测试目录

- `tests/reconciliation/test_shadow_reconciliation.py`

---

## 3. Fuzz 测试

### 3.1 范围

| 目标 | 不变量 |
| --- | --- |
| RunSpec | YAML 解析不应崩溃，必填字段必填 |
| BarSequence | 乱序/重复/缺失 bar 不应崩溃 orchestrator |
| UniverseSnapshot | 异常时间元组不应通过 validate |
| ComposerDecision | 单 binding + 多 binding 不应崩溃 |

### 3.2 实现方式

- 使用 `random.Random(seed)` 控制可复现
- 100-1000 次迭代
- 每次迭代：构造随机输入 → 调用目标 API → 断言不崩溃
- 失败应捕获异常并报告，不应让进程崩溃

### 3.3 测试目录

- `tests/fuzz/test_runspec_fuzz.py`
- `tests/fuzz/test_bar_sequence_fuzz.py`
- `tests/fuzz/test_universe_fuzz.py`
- `tests/fuzz/test_composer_fuzz.py`

---

## 4. Benchmark

### 4.1 目标

| 项 | 基线 |
| --- | --- |
| Bar throughput | ≥ 10000 bars/s |
| 多 symbol 扩展 | 100 symbols 内存 < 200MB |
| Memory per bar | ≤ 20KB |
| 启动时间 | < 1s |

### 4.2 测试目录

- `tests/benchmark/benchmark_backtest.py`

### 4.3 文档目录

- `docs/benchmark/benchmark-20260703.md`

---

## 5. 与已有体系的关系

| 既有 | Phase 7 新增 |
| --- | --- |
| `tests/property/test_determinism.py` | — |
| `tests/golden/*` | — |
| `tests/contract/*` | — |
| — | `tests/consistency/*` |
| — | `tests/reconciliation/*` |
| — | `tests/fuzz/*` |
| — | `tests/benchmark/*` |
| `docs/observability/*` | — |
| — | `docs/benchmark/*` |

---

## 6. 交付物

| 文件 | 职责 |
| --- | --- |
| `docs/architecture/backtest-phase7-design.md` | Phase 7 设计（本文件） |
| `tests/consistency/test_replay_consistency.py` | C1-C6 replay |
| `tests/consistency/test_live_vs_replay.py` | live vs shadow |
| `tests/reconciliation/test_shadow_reconciliation.py` | shadow 比较 |
| `tests/fuzz/test_runspec_fuzz.py` | run spec fuzz |
| `tests/fuzz/test_bar_sequence_fuzz.py` | bar 序列 fuzz |
| `tests/fuzz/test_universe_fuzz.py` | universe fuzz |
| `tests/fuzz/test_composer_fuzz.py` | composer fuzz |
| `tests/benchmark/benchmark_backtest.py` | 性能基准 |
| `docs/benchmark/benchmark-20260703.md` | 基准文档 |
| `docs/reviews/phase-7-review.md` | Phase 7 Review |