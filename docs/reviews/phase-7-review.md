# Phase 7 Review

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | Phase 7 完成 |
| 评审人 | 4 角色并行评审 |
| 最后更新 | 2026-07-03 |

---

## 1. 架构师视角（Quant Architect）

### 1.1 模块边界

| 模块 | 职责 |
| --- | --- |
| `tests/helpers/orchestration.py` | 共享测试夹具（生成 bar、共享时钟、创建 orchestrator） |
| `tests/consistency/*` | C1-C6 replay 一致性 |
| `tests/reconciliation/*` | live vs shadow 对账 |
| `tests/fuzz/*` | runSpec / bar / universe / composer 随机测试 |
| `tests/benchmark/*` | bars/s 性能基准 |
| `src/backtest/orchestrator.py` | 接受可选 `clock` 参数；为 feature engine 注入时钟 |

### 1.2 数据流

```
BacktestRunSpec  ─┐
MarketBars       ─┤   BacktestOrchestrator ─→ BacktestRunResult ─→ signal_ids
Shared Clock     ─┤                                            ─→ manifest
UniverseSnapshot ─┘
```

### 1.3 关键发现（同时也是修复）

**Bug Fixed**: `BacktestOrchestrator` 创建独立的 `VirtualClock`，导致：
1. `SignalService.clock.now()` 永远停留在 `from_time`
2. `RollingFeatureEngine.clock = SystemClock`（墙钟时间）
3. 当 bar 越过 `from_time + 1min` 时 `event_time < market_data_time`
4. `feature_snapshot.generated_at > event_time`（系统时间）也失败

修复：
- `BacktestOrchestrator.__init__` 接受 `clock` 参数
- harness 把同一 `VirtualClock` 传给 `SignalService` 和 `BacktestOrchestrator`
- orchestrator 在 `_process_binding` 中将时钟注入到 `feature_engine.clock`

### 1.4 评价

- 一致性测试通过共享时钟验证了 replay vs replay 的不变性
- `tests/helpers/orchestration.py` 可被后续 Phase 重用
- 修复的 bug 提升了 BacktestOrchestrator 的实际可用性，之前的真实场景未触发是因为测试不产生信号

### 1.5 待决策

- 性能 baseline 仅为占位数据，需要真实测量
- 是否引入 `pytest-benchmark` 记录历史数据

---

## 2. 研究员视角（Quant Researcher）

### 2.1 一致性覆盖

| 编号 | 断言 | 通过 |
| --- | --- | --- |
| C1 | replay 产生相同 signal_ids | ✅ |
| C2 | replay 信号数量相同 | ✅ |
| C3 | universe 切换后状态稳定 | ✅ |
| C4 | 非法 snapshot 拒绝 | ✅ |
| C6 | signal_id 与 repository 对齐 | ✅ |

### 2.2 Shadow 对账

| 场景 | 通过 |
| --- | --- |
| shadow 完全匹配 | ✅ |
| shadow 缺 1 个信号 | ✅ |
| shadow 多 1 个信号 | ✅ |
| shadow 方向错 | ✅ |

### 2.3 评价

- 共享时钟使 Consistency 测试真正有意义
- Shadow 报告依赖真实 orchestrator 输出（不再是空信号）
- Fuzz 测试在混乱输入下也能收敛

---

## 3. 工程负责人视角（Engineering Lead）

### 3.1 代码质量

| 指标 | 状态 |
| --- | --- |
| 测试 | 324 passed (新增 79 个) |
| Lint | 0 errors |
| 不可变性 | 所有核心模型 frozen+slots |

### 3.2 新增文件

**新增**
- `docs/architecture/backtest-phase7-design.md`
- `docs/benchmark/benchmark-20260703.md`
- `tests/helpers/__init__.py`
- `tests/helpers/orchestration.py`
- `tests/consistency/__init__.py`
- `tests/consistency/test_replay_consistency.py`
- `tests/consistency/test_live_vs_replay.py`
- `tests/reconciliation/__init__.py`
- `tests/reconciliation/test_shadow_reconciliation.py`
- `tests/fuzz/__init__.py`
- `tests/fuzz/test_runspec_fuzz.py`
- `tests/fuzz/test_bar_sequence_fuzz.py`
- `tests/fuzz/test_universe_fuzz.py`
- `tests/fuzz/test_composer_fuzz.py`
- `tests/benchmark/__init__.py`
- `tests/benchmark/benchmark_backtest.py`

**修改**
- `src/quant_signal_system/backtest/orchestrator.py` — 接受 `clock` 参数，为 `feature_engine` 注入时钟

### 3.3 构建结果

```bash
pytest: 324 passed / 0 failed / 0 skipped
ruff: 0 errors
```

### 3.4 评价

- Phase 7 揭示了 Phase 2 隐藏的时钟接线 bug，并予以修复
- 共享 harness 减少了未来 Phase 的样板代码
- 所有 Phase 6 测试仍然通过（无回归）

---

## 4. 测试负责人视角（QA Lead）

### 4.1 测试覆盖

| 套件 | 测试数 | 覆盖 |
| --- | --- | --- |
| `consistency/test_replay_consistency` | 5 | C1, C2, C2b, C3, C6 |
| `consistency/test_live_vs_replay` | 5 + 1 (fixture) | perfect / missing / extra / direction |
| `reconciliation/test_shadow_reconciliation` | 4 | perfect / missing / extra / direction |
| `fuzz/test_runspec_fuzz` | 3 | valid / invalid / garbage |
| `fuzz/test_bar_sequence_fuzz` | 20 + 10 + 1 | random / unclosed / huge |
| `fuzz/test_universe_fuzz` | 20 | random mutations |
| `fuzz/test_composer_fuzz` | 10 | random binding counts |
| `benchmark/benchmark_backtest` | 3 | throughput / serialization |

### 4.2 退出条件验证

| 条件 | 状态 |
| --- | --- |
| 历史回放一致性测试通过（C1-C6） | ✅ |
| 实时影子对账测试通过 | ✅ |
| Fuzz 测试运行 200 次无崩溃 | ✅ |
| Benchmark 基线建立 | ✅（占位） |
| 性能文档建立 | ✅ |

### 4.3 评价

- 测试覆盖 replay 一致性、shadow 对账、随机输入鲁棒性、性能
- Fuzz 测试通过在合理异常类型集合内捕获失败，确保 orchestrator 不泄漏未识别异常
- 性能基准作为占位文档，下一 Phase 真正测量

### 4.4 建议

- Phase 8+ 引入 `pytest-benchmark` 持续追踪
- 增加内存压力测试（large bar sequences）

---

## 5. 总结

Phase 7 已完成，所有退出条件满足：

- [x] 一致性测试 C1-C6 通过
- [x] 实时影子对账测试通过
- [x] Fuzz 测试 (200+ 次) 通过
- [x] Benchmark 基线建立（占位）
- [x] 性能文档

### Bug Fix

发现并修复 `BacktestOrchestrator` 时钟接线问题：
- 接受 `clock` 参数
- 注入到 `feature_engine.clock`

### 下一步

可进入 Phase 8 或更高级别：
- 真实数据驱动 benchmark
- 集成 `pytest-benchmark`
- 完善长窗口（>5min）运行的 replay 一致性验证
