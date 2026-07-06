# Phase 3 Review：多策略组合与审计

## 文档信息

| 项目 | 内容 |
| --- | --- |
| Phase | 3 — 多策略组合与审计 |
| 评审日期 | 2026-07-03 |
| 评审人 | A（架构）、B（量化正确性）、C（测试与可靠性）、D（性能与工程） |
| 基线 | 204 passed / 0 failed / 0 skipped |
| Linter | ruff: 0 errors（3 unused imports auto-fixed） |
| Type checker | pyright: 0 errors on Phase 3 files |
| 新增测试 | 19 tests（185 → 204） |

---

## Reviewer A：架构与模块边界

### A.1 模块职责检查

| 模块 | 文件 | 状态 | 评价 |
| --- | --- | --- | --- |
| ComposerDecision | `strategies/composer_decision.py` | ✅ | 不可变审计记录，幂等持久化接口 |
| ComposerDecisionRepository | `strategies/composer_decision.py` | ✅ | 追加写入、按 binding/symbol 查询 |
| StrategyComposer.decide() | `strategies/composer.py` | ✅ | Phase 3 API，与 `on_bar()` 并行，不破坏兼容性 |
| OrderIntent | `backtest/order_intent.py` | ✅ | 信号到执行的桥接层，不可变 |

### A.2 依赖方向检查

```
strategies/composer_decision.py  →  composer.py (SignalCandidate), datetime（单向）
strategies/composer.py           →  composer_decision.py（通过 decide()）
backtest/order_intent.py         →  contracts/signals.py（单向）
strategies/__init__.py           →  导出 ComposerDecision + Repository
backtest/__init__.py             →  导出 OrderIntent
```

**结论：无循环依赖。** `composer.py` 的 `decide()` 在方法内部懒加载 `composer_decision.py`，避免顶层循环。

### A.3 数据所有权

| 类 | 所有权 | 评估 |
| --- | --- | --- |
| `ComposerDecision` | `strategies/` 模块 | ✅ |
| `ComposerDecisionRepository` | `strategies/` 模块 | ✅ |
| `OrderIntent` | `backtest/` 模块 | ✅ |

### A.4 关键设计决策

#### Decision 1：`decide()` 与 `on_bar()` 并行

`on_bar()` 保留 Phase 1/2 API（返回 `SignalCandidate | None`）。`decide()` 是 Phase 3 API（返回 `(SignalCandidate | None, ComposerDecision)`）。两者产生相同的信号输出；`decide()` 额外提供审计记录。

**影响**：Phase 0/1/2 代码（`BacktestRunner`、`BacktestOrchestrator`）继续使用 `on_bar()`，无需修改。

#### Decision 2：ComposerDecision 幂等写入

`ComposerDecisionRepository.append()` 对相同 `decision_id` 返回现有记录；不同内容则报 `ComposerDecisionConflictError`。这是审计链路的正确性保证：重复写入不会静默覆盖。

#### Decision 3：OrderIntent.from_signal()

`OrderIntent` 从 `SignalEvent` 派生，使用确定性 `intent_id`（基于 `signal_id`）。Phase 3 使用固定 100 股手数；Phase 4 用实际持仓状态细化。

### A.5 扩展性评估

| 点 | 评估 |
| --- | --- |
| 新增 ComposerDecision 字段 | ✅ frozen dataclass，需新版本或 `replace()` |
| OrderIntent 持久化 | ✅ Phase 3 接口已就绪，Phase 4 使用 |
| 多策略回测（同一 Binding） | ✅ `StrategyComposer(runtimes=(r1, r2, ...))` |
| 多策略回测（不同 Binding） | ✅ 各 Binding 独立 `StatePartition` |

### A.6 发现

| 编号 | 级别 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| A-01 | Minor | `BacktestOrchestrator` 未在 Phase 3 集成 `StrategyComposer` | 预期行为；Phase 3 专注于接口和审计，集成留 Phase 3 末尾或 Phase 4 |
| A-02 | Suggestion | `OrderIntent` 的 `from_signal` 固定 100 股 | Phase 4 细化（接受） |
| A-03 | Suggestion | `ComposerDecisionRepository` 缺少 `remove()` 方法 | 审计日志应只增不删，无需移除 |

---

## Reviewer B：量化正确性

### B.1 前视偏差防护

| 检查点 | 状态 | 实现位置 |
| --- | --- | --- |
| `ComposerDecision.decision_id` 确定性生成 | ✅ | `_composer_decision_id()` 使用 SHA-256 |
| `OrderIntent.intent_id` 确定性生成 | ✅ | `_order_intent_id()` 使用 SHA-256 |
| `decide()` 与 `on_bar()` 相同信号输出 | ✅ | `test_decide_and_on_bar_produce_same_candidate` |
| 不可变 ComposerDecision | ✅ | `frozen=True, slots=True` |

### B.2 数据泄漏防护

| 检查点 | 状态 | 说明 |
| --- | --- | --- |
| ComposerDecision 不修改 SignalEvent | ✅ | 独立不可变对象 |
| OrderIntent 不修改 SignalEvent | ✅ | 独立不可变对象 |
| 决策 ID 与信号 ID 独立 | ✅ | 不同命名空间 |

### B.3 量化语义正确性

| 语义 | 状态 | 评估 |
| --- | --- | --- |
| ComposerDecision 幂等写入 | ✅ | `test_append_same_twice_returns_existing` |
| ComposerDecision 冲突检测 | ✅ | `test_append_same_id_different_content_raises` |
| OrderIntent 数量非负 | ✅ | `__post_init__` 校验 |
| OrderIntent 不可变 | ✅ | `frozen=True, slots=True` |
| 方向冲突归因 | ✅ | `test_direction_conflict_attributed` |
| 全票失败归因 | ✅ | `test_unanimous_failure_attributed` |
| 权重为零归因 | ✅ | `test_score_weighted_zero_attributed` |

### B.4 Phase 2 Review 问题修复验证

| 编号 | 问题 | Phase 2 建议 | Phase 3 状态 |
| --- | --- | --- | --- |
| B-02 | UniverseResolver 切换时重查询 | Phase 2 修复 | ✅ 延续 Phase 2 实现 |
| D-03 | 双重存储不一致 | Phase 2 修复 | ✅ 延续 Phase 2 修复 |
| C-01 | 无 Universe 切换测试 | Phase 3 补充 | 已有 Universe 变化测试 Phase 2 中 |

### B.5 关键发现

| 编号 | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| B-01 | Minor | OrderIntent.from_signal 对 REDUCE_LONG/CLEAR_LONG 设 quantity=100（未检查实际持仓） | Phase 4 细化为实际可卖数量 |
| B-02 | Suggestion | ComposerDecision 未包含 SignalEvent 的 feature_snapshot 引用 | Phase 5 评价时可能需要 |

---

## Reviewer C：测试与可靠性

### C.1 测试覆盖矩阵

| 测试类 | 测试数 | 覆盖点 |
| --- | --- | --- |
| `TestComposerDecisionIdempotency` | 5 | 幂等写入、冲突检测、按 binding/symbol 查询 |
| `TestComposerDecisionAttribution` | 6 | 方向冲突、全票失败、权重为零、无拒绝、拒绝原因、decide/on_bar 一致性 |
| `TestOrderIntentFromSignal` | 7 | BUY/SELL/REDUCE/CLEAR 数量、确定性、校验、不可变 |
| **Phase 3 新增总计** | **19** | |
| **Phase 1+2 遗留** | **185** | |
| **当前总计** | **204** | |

### C.2 边界条件覆盖

| 场景 | 测试 | 状态 |
| --- | --- | --- |
| 相同 decision_id 重复写入 | `test_append_same_twice_returns_existing` | ✅ |
| 相同 decision_id 不同内容 | `test_append_same_id_different_content_raises` | ✅ |
| 方向冲突归因 | `test_direction_conflict_attributed` | ✅ |
| 全票失败归因 | `test_unanimous_failure_attributed` | ✅ |
| 权重为零归因 | `test_score_weighted_zero_attributed` | ✅ |
| decide/on_bar 一致性 | `test_decide_and_on_bar_produce_same_candidate` | ✅ |
| REDUCE_LONG 保留数量 | `test_reduce_long_keeps_quantity` | ✅ |
| CLEAR_LONG 保留数量 | `test_clear_long_keeps_quantity` | ✅ |

### C.3 可靠性发现

| 编号 | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| C-01 | Minor | 无 ComposerDecision 在 BacktestOrchestrator 中的集成测试 | Phase 3 末尾或 Phase 4 补充 |
| C-02 | Suggestion | 无 OrderIntent 持久化测试（OrderIntentRepository 尚未实现） | Phase 3 末尾或 Phase 4 实现 |
| C-03 | Suggestion | `_signal()` 辅助函数在多个测试文件中重复 | 建议抽取到 `tests/fixtures/` |

### C.4 幂等性验证

| 操作 | 幂等键 | 验证 |
| --- | --- | --- |
| `ComposerDecisionRepository.append()` | `decision_id` | ✅ `test_append_same_twice_returns_existing` |
| `OrderIntent.from_signal()` | `signal_id` | ✅ `test_deterministic_intent_id` |
| `StrategyComposer.decide()` | `(binding_id, market_data_time, symbol, policy)` | ✅ 通过 decision_id 验证 |

---

## Reviewer D：性能与工程质量

### D.1 时间复杂度

| 操作 | 复杂度 | 评估 |
| --- | --- | --- |
| `ComposerDecisionRepository.append()` | O(1) | ✅ dict 写入 |
| `ComposerDecisionRepository.get()` | O(1) | ✅ dict 查找 |
| `ComposerDecisionRepository.list_for_binding()` | O(n) | ⚠️ 线性扫描；Phase 3 规模小可接受 |
| `ComposerDecisionRepository.list_for_symbol()` | O(n) | ⚠️ 同上 |
| `StrategyComposer.decide()` | O(m) | ✅ m=runtime 数 |
| `OrderIntent.from_signal()` | O(1) | ✅ SHA-256 + 字段赋值 |
| `_composer_decision_id()` | O(1) | ✅ SHA-256 固定输入 |

### D.2 内存复杂度

| 结构 | 评估 |
| --- | --- |
| `ComposerDecisionRepository._records` | O(n)，n=决策数 |
| `StrategyComposer`（frozen） | O(m)，m=runtime 数 |
| `OrderIntent`（frozen） | O(1) |

**无内存泄漏风险。**

### D.3 类型和异常设计

| 方面 | 评估 |
| --- | --- |
| 所有新类 `frozen=True, slots=True` | ✅ |
| `__all__` 显式导出 | ✅ |
| Docstring 存在 | ✅ |
| 公开接口类型标注 | ✅ |
| `__post_init__` 校验 | ✅ `OrderIntent` 校验 intent_id/signal_id/quantity |

### D.4 新增依赖评估

| 依赖 | 用途 | 评估 |
| --- | --- | --- |
| `hashlib`（Python 内置） | 确定性 ID 生成 | ✅ 无新增 |
| 无其他新增依赖 | — | ✅ |

**Phase 3 未引入任何新依赖。**

### D.5 工程发现

| 编号 | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| D-01 | Minor | `StrategyComposer.decide()` 在方法内 lazy import `ComposerDecision` | 必要措施（避免循环导入）；可记录为已知模式 |
| D-02 | Suggestion | `list_for_binding` / `list_for_symbol` O(n) | Phase 4 或数据量大时考虑二级索引 |
| D-03 | Minor | `OrderIntent` 的 `created_at` 使用 `datetime.now(timezone.utc)`（非确定性） | 审计场景可接受；若需确定性测试应使用注入时钟 |

---

## 综合结论

### 修复情况

| 编号 | 级别 | 问题 | 是否修复 |
| --- | --- | --- | --- |
| A-01 | Minor | BacktestOrchestrator 未集成 Composer | 记录（Phase 3 预期范围） |
| B-01 | Minor | OrderIntent 未检查实际持仓 | 记录（Phase 4） |
| C-01 | Minor | 无 Orchestrator 集成测试 | 记录（Phase 3/4） |
| D-01 | Minor | lazy import | 已知模式，无需修复 |

**所有 Blocker 数量：0**

### 遗留风险

| 编号 | 风险 | 缓解 |
| --- | --- | --- |
| RISK-01 | `OrderIntent` 固定 100 股手数 | Phase 4 细化为实际持仓 |
| RISK-02 | `OrderIntent.created_at` 非确定性 | Phase 4 注入时钟 |
| RISK-03 | `list_for_binding` O(n) | 当前规模可接受；数据量大时索引 |

### 是否满足 Phase 3 验收条件

| 验收条件 | 状态 |
| --- | --- |
| ComposerDecision 持久化测试通过（重复写入幂等） | ✅ 5 个幂等测试全部通过 |
| 冲突场景归因正确 | ✅ 方向冲突、全票失败、权重为零 |
| ComposerCandidate.rejection_reason 正确填充 | ✅ 所有拒绝原因已填充 |
| decide() 与 on_bar() 产生相同候选 | ✅ `test_decide_and_on_bar_produce_same_candidate` |
| ruff lint | ✅ 0 errors |
| pyright type check | ✅ 0 errors |
| 现有测试未破坏 | ✅ 185 → 204（+19） |

**Phase 3 验收通过。建议进入 Phase 4。**

### 建议进入下一阶段

**是。** Phase 3 的多策略组合审计和 OrderIntent 生成已完成。`ComposerDecision` 提供了完整的冲突归因审计链路，`OrderIntent` 为 Phase 4 的执行层提供了清晰的桥接接口。

---

## Phase 3 交付物总结

### 修改文件列表

**新增文件（3个）**
- `docs/architecture/backtest-phase3-design.md` — Phase 3 架构设计补充
- `src/quant_signal_system/strategies/composer_decision.py` — `ComposerDecision` + Repository
- `src/quant_signal_system/backtest/order_intent.py` — `OrderIntent`

**修改文件（2个）**
- `src/quant_signal_system/strategies/composer.py` — 增加 `decide()` Phase 3 API
- `src/quant_signal_system/strategies/__init__.py` — 导出 `ComposerDecision` 等

**新增测试文件（2个）**
- `tests/strategies/test_composer_decision.py` — 11 tests
- `tests/backtest/test_order_intent.py` — 8 tests

### 关键设计决策

| 决策 | 影响 |
| --- | --- |
| `decide()` 与 `on_bar()` 并行 | Phase 0-2 代码无需修改 |
| ComposerDecision 幂等写入 | 审计链路正确性保证 |
| OrderIntent 确定性 ID | 信号-执行链路可追溯 |
| OrderIntent 固定 100 股 | Phase 4 细化（可接受） |

### 测试命令和结果

```bash
pytest (all tests): 204 passed / 0 failed / 0 skipped
ruff: 0 errors (3 unused imports auto-fixed)
pyright (Phase 3): 0 errors / 0 warnings
```

### 遗留风险

1. **RISK-01（低）**：OrderIntent 固定 100 股，Phase 4 细化
2. **RISK-02（低）**：OrderIntent created_at 非确定性，Phase 4 注入时钟
3. **RISK-03（低）**：ComposerDecisionRepository 查询 O(n)，数据量大时索引
