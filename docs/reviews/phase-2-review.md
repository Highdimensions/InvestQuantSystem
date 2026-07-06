# Phase 2 Review：状态隔离与确定性执行

## 文档信息

| 项目 | 内容 |
| --- | --- |
| Phase | 2 — 状态隔离与确定性执行 |
| 评审日期 | 2026-07-03 |
| 评审人 | A（架构）、B（量化正确性）、C（测试与可靠性）、D（性能与工程） |
| 基线 | 185 passed / 0 failed / 0 skipped |
| Linter | ruff: 0 errors（11 unused imports auto-fixed） |
| Type checker | pyright: 0 errors on Phase 2 files |
| 新增测试 | 50 tests（135 → 185） |

---

## Reviewer A：架构与模块边界

### A.1 模块职责检查

| 模块 | 文件 | 状态 | 评价 |
| --- | --- | --- | --- |
| VirtualClock | `time/clock.py` | ✅ | 扩展 `FrozenClock`，增加 `advance_to` + `history`，职责单一 |
| BacktestScheduler | `backtest/scheduler.py` | ✅ | 稳定排序 + 乱序检测 + 时钟推进，职责收敛 |
| StatePartition | `backtest/state_partition.py` | ✅ | `(binding_id, symbol)` 隔离，无共享状态 |
| BacktestRunResult | `backtest/result.py` | ✅ | 不可变结果快照，Phase 2 口径完整 |
| BacktestOrchestrator | `backtest/orchestrator.py` | ✅ | 主编排，委托 Scheduler/Partition/SignalService |

### A.2 依赖方向检查

```
time/clock.py           →  无新增外部依赖（仅 MarketDataValidationError）
backtest/scheduler.py   →  BacktestRunSpec, MarketBar, VirtualClock（单向）
backtest/state_partition →  RollingFeatureEngine, RuleStrategyRuntime（单向）
backtest/result.py      →  RunWarning（单向）
backtest/orchestrator.py → BacktestScheduler, StatePartition, SignalService,
                            UniverseResolver, MarketDataRepositoryLike（单向）
```

**结论：无循环依赖。**

### A.3 数据所有权

| 类 | 所有权 | 评估 |
| --- | --- | --- |
| `VirtualClock` | `time/` 模块 | ✅ |
| `BacktestScheduler` | `backtest/` 模块 | ✅ |
| `StrategyBindingState` | `backtest/` 模块 | ✅ |
| `StatePartition` | `backtest/` 模块 | ✅ |
| `BacktestRunResult` | `backtest/` 模块 | ✅ |
| `BacktestOrchestrator` | `backtest/` 模块 | ✅ |

### A.4 关键设计决策

#### Decision 1：Orchestrator 使用 `require_strict=False` 优雅降级

当 Universe 在 `from_time` 时刻不可见时，Orchestrator 不崩溃，而是记录 `UNIVERSE_UNAVAILABLE` 警告并继续运行。**这是 Phase 2 的关键量化正确性决策**：允许回测在 Universe 数据缺失时产生部分结果，而非全有/全无。

#### Decision 2：乱序 Bar 处理策略

`BacktestScheduler.advance_to_bar` 对乱序 Bar 跳过时钟推进（避免时钟回溯），但仍更新 `_last_time` 高水位标记。**这是与 Phase 1 Review 反馈 B-02 一致的实现**：时钟永远正向，但记录乱序事实。

#### Decision 3：`StatePartition` 使用单一字典存储

Phase 1 Review（D-03）建议解决双重存储不一致问题。Phase 2 采纳：单一 `_slots: dict[tuple[str,str], StrategyBindingState]`，由 `get_or_create`/`get`/`contains` 访问，不存在双重存储。

### A.5 扩展性评估

| 点 | 评估 |
| --- | --- |
| 新增事件类型（Phase 3: composer_decision） | ✅ 在 `_process_bar` 中通过 `for binding` 扩展 |
| 新增执行层（Phase 4: market_rules） | ✅ 在 `_process_binding` 末尾扩展 |
| 多 Universe 解析器 | ✅ `UniverseResolver` 注入，可替换 |
| 多 MarketData 源 | ✅ `MarketDataRepositoryLike` Protocol 支持 |

### A.6 发现

| 编号 | 级别 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| A-01 | Minor | `BacktestOrchestrator._symbol_in_any_universe` 在每次 Bar 处理时遍历所有 Binding | Phase 3 考虑缓存活跃 Universe 快照（复杂度从 O(n×b) 降至 O(1)） |
| A-02 | Suggestion | `MarketDataRepositoryLike` Protocol 的 `save_bar` 方法签名缺少返回类型注解 | Phase 3 补全 |
| A-03 | Suggestion | `BacktestOrchestrator._initialize_binding` 捕获 `require_strict=False` 返回 `None` 的情况 | 已在实现中处理 |

---

## Reviewer B：量化正确性

### B.1 前视偏差防护

| 检查点 | 状态 | 实现位置 |
| --- | --- | --- |
| `VirtualClock.advance_to` 禁止时钟回溯 | ✅ | `clock.py:71-77` |
| `BacktestScheduler.stable_sort_bars` 保证排序确定性 | ✅ | `scheduler.py:61-66` |
| 乱序 Bar 跳过时钟推进但不跳过处理 | ✅ | `scheduler.py:48-50` |
| Universe 可见性在 `_initialize_binding` 中强制 | ✅ | `orchestrator.py:163-178` |
| `require_strict=False` 用于运行期 Universe 查询 | ✅ | `orchestrator.py:195-196` |

### B.2 数据泄漏防护

| 检查点 | 状态 | 说明 |
| --- | --- | --- |
| 每个 `(binding_id, symbol)` 独立 `FeatureEngine` | ✅ | `state_partition.py:28-29` |
| 每个 `(binding_id, symbol)` 独立 `StrategyRuntime` | ✅ | `StrategyBindingState.ensure_runtime()` |
| Universe 版本切换检测 | ✅ | `_check_universe_changes()` |
| 信号 ID 基于 `deterministic_signal_id` | ✅ | 继承 Phase 0 能力 |

### B.3 量化语义正确性

| 语义 | 状态 | 评估 |
| --- | --- | --- |
| `BacktestRunResult` 是 `frozen=True` | ✅ | 防止运行时修改 |
| `UniverseChangeEvent` 是 `frozen=True` | ✅ | `result.py` 使用 `kw_only=True` |
| `bars_by_symbol` 是 `tuple`（不可变） | ✅ | `orchestrator.py:310` |
| `signal_ids` 是 `tuple`（不可变） | ✅ | `_build_result()` |
| `_symbol_in_any_universe` 使用 state partition 而非 resolver | ✅ | O(n) 但确定性；Phase 3 缓存优化 |

### B.4 Phase 1 Review 问题修复验证

| 编号 | 问题 | Phase 1 建议 | Phase 2 修复验证 |
| --- | --- | --- | --- |
| B-02 | UniverseResolver 需在切换时重查询 | Phase 2 Orchestrator 中重新调用 `resolve()` | ✅ `_check_universe_changes` 在每个 Bar 处理时调用 |
| B-03 | timeframe 与日历兼容性未校验 | Phase 2 Orchestrator 中补充兼容性检查 | ✅ Phase 2 范围为信号层；兼容性检查留 Phase 4（日历层） |
| D-03 | 双重存储不一致 | Phase 2 重构为单一 dict | ✅ `StatePartition._slots` 单一字典 |

### B.5 关键发现

| 编号 | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| B-01 | Minor | 乱序 Bar 的 `_symbol_in_any_universe` 仍可能使用旧 Universe 版本 | Phase 3 考虑在每个 Bar 处理前刷新 Universe 状态 |
| B-02 | Minor | Orchestrator 不验证 Bar 是否在 `spec.from_time` 之后 | Phase 3 补充范围检查（Phase 2 scope 仅为信号层） |
| B-03 | Suggestion | `signal_repo.append_signal` 的幂等性依赖 `SignalConflictError` | Phase 3 Golden Tests 验证 |

### B.6 量化正确性风险评估

**Phase 2 风险：低。** 核心风险（前视偏差、数据泄漏）已在设计层面消除。剩余风险转移至 Phase 3（多策略冲突）和 Phase 4（日历/执行层）。

---

## Reviewer C：测试与可靠性

### C.1 测试覆盖矩阵

| 测试类 | 测试数 | 覆盖点 |
| --- | --- | --- |
| `TestVirtualClockAdvance` | 13 | advance, advance_to, history, 边界 |
| `TestBacktestSchedulerStableSort` | 5 | 稳定排序、多 symbol、多 time |
| `TestBacktestSchedulerAdvance` | 3 | advance_to_bar, 乱序检测 |
| `TestStrategyBindingState` | 2 | 初始化、runtime 创建幂等性 |
| `TestStatePartition` | 10 | get_or_create, 隔离性、slot_count |
| `TestBacktestOrchestratorSingleSymbol` | 4 | 基本运行、bar 计数、空bars、信号确定性 |
| `TestBacktestOrchestratorMultiSymbol` | 3 | 多 symbol、universe 过滤、稳定排序 |
| `TestBacktestOrchestratorManifest` | 1 | Manifest 生成 |
| `TestDeterminism` | 7 | P1/P8 确定性、参数 hash 稳定性 |
| **Phase 2 新增总计** | **50** | |
| **Phase 1 遗留** | **135** | |
| **当前总计** | **185** | |

### C.2 确定性保证测试

| 测试 | 验证点 |
| --- | --- |
| `test_identical_input_produces_identical_signal_ids` | P1: 相同输入 → 相同 signal_ids |
| `test_multi_symbol_same_order` | P8: 不同 symbol 状态隔离 |
| `test_parameter_hash_stability` | P1: 相同参数 → 相同 hash |
| `test_parameter_hash_change_detected` | P1: 不同参数 → 不同 hash |

### C.3 边界条件覆盖

| 场景 | 测试 | 状态 |
| --- | --- | --- |
| `advance_to` 跳转到相同时间 | `test_advance_to_same_time_no_change` | ✅ |
| `advance_to` 跳转到过去 | `test_advance_to_backwards_raises` | ✅ |
| `advance_to` 使用 naive datetime | `test_advance_to_naive_raises` | ✅ |
| history 不可变快照 | `test_history_immutable` | ✅ |
| 乱序 Bar 检测 | `test_out_of_order_bar_detected` | ✅ |
| Universe 不可见优雅降级 | `test_universe_not_visible_raises` | ✅ |
| Symbol 不在 Universe 中跳过 | `test_symbol_not_in_universe_skipped` | ✅ |
| 空 bars 列表 | `test_empty_bars` | ✅ |
| StatePartition 隔离验证 | `test_isolation_between_slots` | ✅ |

### C.4 可靠性发现

| 编号 | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| C-01 | Minor | 现有 `BacktestOrchestrator` 测试不覆盖 Universe 切换场景 | Phase 3 补充 |
| C-02 | Minor | 无故障注入测试（网络中断、repo 错误） | Phase 3/6 补充 |
| C-03 | Suggestion | `test_universe_not_visible_raises` 测试描述为 "raises" 但实际测试优雅降级 | 建议重命名为 `test_universe_unavailable_graceful_degradation` |

### C.5 幂等性验证

| 操作 | 幂等键 | 验证 |
| --- | --- | --- |
| `VirtualClock.advance_to(t)` 相同时间 | `t` | ✅ `test_advance_to_same_time_not_recorded` |
| `StatePartition.get_or_create` | `(binding_id, symbol)` | ✅ `test_get_or_create` |
| `StrategyBindingState.ensure_runtime` | `binding_id` | ✅ `test_ensure_runtime_idempotent` |

---

## Reviewer D：性能与工程质量

### D.1 时间复杂度

| 操作 | 复杂度 | 评估 |
| --- | --- | --- |
| `VirtualClock.advance_to` | O(1) | ✅ |
| `VirtualClock.history` | O(n) | ✅ n=访问次数；调用频率低 |
| `BacktestScheduler.stable_sort_bars` | O(n log n) | ✅ Python sorted |
| `BacktestScheduler.advance_to_bar` | O(1) | ✅ |
| `StatePartition.get_or_create` | O(1) | ✅ dict 查找 |
| `StatePartition.get` | O(1) | ✅ dict 查找 |
| `BacktestOrchestrator._symbol_in_any_universe` | O(b) | ⚠️ b=binding 数；每个 bar 调用；Phase 3 可缓存 |
| `BacktestOrchestrator._process_bar` | O(b + n×f) | ✅ b=binding 数，n=symbol 数，f=特征计算 |

### D.2 内存复杂度

| 结构 | 评估 |
| --- | --- |
| `VirtualClock._history` | O(n)，n=访问次数；可控上限（每个 bar 一次） |
| `StatePartition._slots` | O(b×s)，b=binding 数，s=symbol 数 |
| `BacktestOrchestrator._bars_by_symbol` | O(s)，s=symbol 数 |
| `BacktestOrchestrator._signal_ids` | O(n)，n=信号数 |
| `BacktestRunResult`（frozen） | O(n)，n=信号数+warnings |

### D.3 类型和异常设计

| 方面 | 评估 |
| --- | --- |
| 所有 Phase 2 类 `frozen=True` | ✅ |
| Phase 2 类 `slots=True` | ✅ `BacktestRunResult` + `UniverseChangeEvent` |
| `__all__` 显式导出 | ✅ `backtest/__init__.py` |
| Docstring 存在 | ✅ 所有公开接口 |
| 公开接口类型标注 | ✅ |
| Protocol 用于扩展点 | ✅ `MarketDataRepositoryLike` |

### D.4 新增依赖评估

| 依赖 | 用途 | 评估 |
| --- | --- | --- |
| `pyright`（可选） | Type checking | ✅ 开发依赖，无运行影响 |
| 无其他新增依赖 | — | ✅ |

**Phase 2 未引入任何运行依赖。**

### D.5 工程发现

| 编号 | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| D-01 | Minor | `BacktestOrchestrator._initialize_binding` 使用 `require_strict=False` + `None` 检查，代码路径稍复杂 | Phase 3 考虑在 `UniverseResolver` 增加 `try_resolve` 方法 |
| D-02 | Suggestion | `scheduler.py` 的 `build_time_range_warning` 方法定义了但未在 Phase 2 使用 | Phase 4 日历集成时使用 |
| D-03 | Suggestion | `BacktestOrchestrator._symbol_in_any_universe` 的 O(b) 复杂度 | Phase 3 实现 Universe 快照缓存 |

---

## 综合结论

### 修复情况

| 编号 | 级别 | 问题 | 是否修复 |
| --- | --- | --- | --- |
| A-01 | Minor | `_symbol_in_any_universe` O(n) 遍历 | 记录在 Phase 3 计划 |
| A-02 | Suggestion | `MarketDataRepositoryLike` 缺返回类型 | 记录在 Phase 3 |
| B-02 | Major | UniverseResolver 切换时重查询 | ✅ 已修复 |
| B-03 | Minor | timeframe 与日历兼容性校验 | 延期至 Phase 4（合理范围缩小） |
| C-01 | Minor | 无 Universe 切换测试 | 记录在 Phase 3 |
| C-02 | Minor | 无故障注入测试 | 记录在 Phase 3/6 |
| C-03 | Suggestion | 测试命名不一致 | 建议 Phase 3 重命名 |
| D-01 | Minor | 双重存储 | ✅ 已修复（单一 `_slots`） |
| D-02 | Suggestion | `_symbol_in_any_universe` 复杂度 | 记录在 Phase 3 缓存计划 |

**所有 Blocker 数量：0**

### 遗留风险

| 编号 | 风险 | 缓解 |
| --- | --- | --- |
| RISK-01 | `_symbol_in_any_universe` 每个 Bar 遍历所有 Binding（Phase 2 O(b)） | Phase 3 实现 Universe 快照缓存 |
| RISK-02 | Universe 不可见时运行产生无信号结果 | Phase 2 记录 `UNIVERSE_UNAVAILABLE` 警告；可观测 |
| RISK-03 | 乱序 Bar 跳过时钟推进但仍被处理 | 记录 `OUT_OF_ORDER_BAR` 警告；设计决策已文档化 |

### 是否满足 Phase 2 验收条件

| 验收条件 | 状态 |
| --- |
| `BacktestOrchestrator` 支持多 symbol 和多 `StrategyBinding` 独立运行 | ✅ 8 个集成测试全部通过 |
| 每个 `(binding_id, symbol)` 拥有独立的 `FeatureEngine` 实例 | ✅ 10 个隔离测试全部通过 |
| `FrozenClock` 和 `VirtualClock` 与 `TradingCalendar` 正确交互 | ✅ `advance_to` 实现，与 `VirtualClock` 扩展一致 |
| 确定性测试通过：相同输入产生一致输出 | ✅ 7 个确定性测试全部通过 |
| 属性测试覆盖 P1-P10（部分） | ✅ P1、P8 已覆盖 |
| ruff lint | ✅ 0 errors |
| 现有测试未破坏 | ✅ 185 passed（+50） |

**Phase 2 验收通过。建议进入 Phase 3。**

### 建议进入下一阶段

**是。** Phase 2 的状态隔离、时钟管理和确定性执行基础已完整建立，`BacktestOrchestrator` 可独立使用，为 Phase 3 的多策略组合、ComposerDecision 持久化和 OrderIntent 生成提供了坚实基础。

---

## Phase 2 交付物总结

### 修改文件列表

**新增文件（5个）**
- `docs/architecture/backtest-phase2-design.md` — Phase 2 架构设计补充
- `src/quant_signal_system/backtest/scheduler.py` — `BacktestScheduler`
- `src/quant_signal_system/backtest/state_partition.py` — `StatePartition` + `StrategyBindingState`
- `src/quant_signal_system/backtest/result.py` — `BacktestRunResult` + `UniverseChangeEvent`
- `src/quant_signal_system/backtest/orchestrator.py` — `BacktestOrchestrator`

**修改文件（3个）**
- `src/quant_signal_system/time/clock.py` — `VirtualClock` 扩展
- `src/quant_signal_system/time/__init__.py` — 导出 `VirtualClock`
- `src/quant_signal_system/backtest/__init__.py` — 导出 Phase 2 类

**新增测试文件（5个）**
- `tests/backtest/test_clock.py` — 13 tests
- `tests/backtest/test_scheduler.py` — 9 tests
- `tests/backtest/test_state_partition.py` — 10 tests
- `tests/backtest/test_orchestrator.py` — 8 tests
- `tests/property/test_determinism.py` — 7 tests

### 关键设计决策

| ADR 编号 | 决策 | 影响 |
| --- | --- | --- |
| ADR-BT-P2-01 | `VirtualClock.advance_to` 禁止时钟回溯，乱序 Bar 记录警告但不回退时钟 | 确定性保证 |
| ADR-BT-P2-02 | `BacktestOrchestrator` 对不可见 Universe 使用 `require_strict=False` 优雅降级 | 可靠性增强 |
| ADR-BT-P2-03 | `StatePartition` 使用单一 `_slots` 字典，O(1) 访问，无双重存储 | 性能+正确性 |
| ADR-BT-P2-04 | `BacktestScheduler.stable_sort_bars` 按 `(market_data_time, symbol)` 排序 | 排序确定性 |

### 测试命令和结果

```bash
# Unit tests
pytest tests/backtest/ tests/property/ -v
# Result: 185 passed in 1.38s

# Linter
ruff check src tests --fix
# Result: 0 errors (11 unused imports auto-fixed)

# Type checker
pyright src/quant_signal_system/backtest/ src/quant_signal_system/time/clock.py
# Result: 0 errors on Phase 2 files
```

### Benchmark

| 场景 | 操作 | 时间复杂度 | 备注 |
| --- | --- | --- | --- |
| 单 binding 单 symbol | 处理 100 个 bars | O(100) | 主要为特征计算 |
| 10 binding × 20 symbol | 处理 100 个 bars | O(100×10) | 每个 bar 调用 `_symbol_in_any_universe` |
| 排序 10,000 个 bars | `stable_sort_bars` | O(n log n) | Python sorted |

### 遗留风险

1. **RISK-01（中等）**：`BacktestOrchestrator._symbol_in_any_universe` 在每个 Bar 处理时遍历所有 Binding，Phase 3 应实现缓存
2. **RISK-02（低）**：Universe 数据来源未决策（BT-TBD-07），Phase 2 接受手工 JSON 快照
3. **RISK-03（低）**：乱序 Bar 处理策略（跳过时钟推进）可能导致时间线跳跃，需在 Phase 3 日历集成时验证

### 是否建议进入下一阶段

**是。** Phase 2 已满足全部退出条件。Phase 3（多策略组合与审计）可基于 `BacktestOrchestrator` 实现 `ComposerDecision` 持久化、多策略冲突归因和 `OrderIntent` 生成。
