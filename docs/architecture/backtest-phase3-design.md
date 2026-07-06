# Phase 3 架构设计补充：多策略组合与审计

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 3 实施 |
| 相关文档 | [Phase 2 设计](./backtest-phase2-design.md)、[执行模型](./backtest-execution-model.md)、[核心领域模型](./backtest-domain-model.md) |
| 最后更新 | 2026-07-03 |

---

## 1. ComposerDecision 持久化

### 1.1 动机

`StrategyComposer.on_bar()` 返回 `SignalCandidate | None`，当多策略冲突时返回 `None`。Phase 3 需要记录：
- 哪些策略参与了决策
- 采用了哪种策略
- 哪些策略被拒绝，为什么
- 最终胜出的信号 ID

### 1.2 ComposerDecision 数据契约

```python
@dataclass(frozen=True, slots=True)
class ComposerDecision:
    schema_version: str = "composer-decision-v1"
    decision_id: str                    # 确定性生成：(binding_id, market_data_time, symbol, policy)
    binding_id: str
    market_data_time: datetime
    symbol: str
    policy: ConflictPolicy
    winning_candidates: tuple[SignalCandidate, ...]  # 胜出的候选
    abstained: bool                     # True = 无信号（冲突/权重为零/全票失败）
    abstention_reason: str | None       #  abstained=True 时记录原因
    rejected_candidates: tuple[SignalCandidate, ...]
    rejection_reasons: tuple[str, ...]
    created_at: datetime
```

### 1.3 持久化接口

```python
class ComposerDecisionRepository:
    """Append-only in-memory repository for ComposerDecision.
    
    幂等写入：同一 decision_id 重复写入返回现有记录（不报错）。
    """
    def append(self, decision: ComposerDecision) -> ComposerDecision: ...
    def get(self, decision_id: str) -> ComposerDecision | None: ...
    def list_for_binding(self, binding_id: str) -> tuple[ComposerDecision, ...]: ...
    def list_for_symbol(self, symbol: str) -> tuple[ComposerDecision, ...]: ...
```

### 1.4 与 Phase 1/2 的关系

- `ComposerDecision` 不修改 `SignalEvent`（append-only 约束）
- `ComposerDecision` 的 `decision_id` 与 `SignalEvent.signal_id` 是独立的 ID 空间
- Phase 2 的 `BacktestRunResult` 增加 `composer_decisions` 字段（可选，Phase 3 启用）

---

## 2. OrderIntent 生成

### 2.1 动机

Phase 3 引入 `OrderIntent` 作为信号到执行的桥接层：
- 信号产生后、执行前，先生成 `OrderIntent`
- `OrderIntent` 包含执行参数（数量、目标价等）
- Phase 4 使用 `OrderIntent` 驱动 `MarketRulesEngine`

### 2.2 OrderIntent 数据契约

```python
@dataclass(frozen=True, slots=True)
class OrderIntent:
    schema_version: str = "order-intent-v1"
    intent_id: str                       # 确定性生成
    signal_id: str                       # 关联的 SignalEvent
    binding_id: str
    symbol: str
    direction: Direction
    action: SignalAction
    quantity: int                        # 整数手（Phase 4 细化）
    reference_price: Decimal
    target_price: Decimal | None         # Phase 4 使用
    executable_time: datetime | None     # Phase 4 使用
    created_at: datetime
```

### 2.3 生成时机

在 `BacktestOrchestrator._process_binding` 中：
1. `candidate = runtime.on_bar(bar, snapshot)` → 候选信号
2. `signal = signal_service.create_event(candidate)` → 信号事件
3. `signal_repo.append_signal(signal)` → 持久化
4. `order_intent = OrderIntent.from_signal(signal, binding_id=binding.binding_id)` → 生成
5. (Phase 4) `order_intent_repo.append(order_intent)` → 持久化

---

## 3. 多策略回测模式

### 3.1 同一 Binding 多策略

```
StrategyBinding(binding_id="multi", composer_policy="PRIORITY_MAX_CONFIDENCE")
  └─ StrategyComposer(runtimes=[RuleStrategyRuntime, MomentumStrategyRuntime])
       └─ _resolve_priority_max_confidence() → 单一 SignalCandidate
            └─ OrderIntent → SignalEvent
```

**特点**：同一 `(binding_id, symbol)` 状态槽中，多个策略共享同一个 `FeatureEngine` 实例（不同策略接收相同特征输入），但各自独立产生候选。

### 3.2 不同 Binding 独立运行

```
StrategyBinding(binding_id="b1", composer_policy="PRIORITY_MAX_CONFIDENCE")
StrategyBinding(binding_id="b2", composer_policy="UNANIMOUS")
```

**特点**：不同 Binding 的 `(binding_id, symbol)` 状态槽完全隔离，包括 `FeatureEngine` 和 `StrategyRuntime`。

### 3.3 隔离保证

| 场景 | FeatureEngine 隔离 | StrategyRuntime 隔离 | Composer 隔离 |
| --- | --- | --- | --- |
| 同一 Binding 多策略 | ✅ 共享（同一状态槽） | ✅ 各自独立 | ✅ 通过 Composer |
| 不同 Binding 同策略 | ✅ 各自独立 | ✅ 各自独立 | ✅ 各自独立 |
| 不同 Binding 不同策略 | ✅ 各自独立 | ✅ 各自独立 | ✅ 各自独立 |

---

## 4. Golden Tests 设计

### 4.1 测试矩阵

| 测试 | 场景 | 验证点 |
| --- | --- | --- |
| G1 | 单 symbol 单策略 | 信号 ID 序列确定性 |
| G2 | 单 symbol 多策略 | Composer 归因 + 信号 ID 序列确定性 |
| G3 | 多 symbol 单策略 | 隔离性（symbol 间不干扰） |
| G4 | 多 symbol 多策略 | Binding × Symbol 隔离 + Composer 归因 |

### 4.2 确定性保证

所有 Golden Tests 要求：
- 相同输入（bars + bindings + params）→ 相同 signal_ids
- 相同输入 → 相同 order_intent_ids
- 相同输入 → 相同 composer_decision_ids

---

## 5. 与 Phase 2 的差异

| Phase 2 设计 | Phase 3 实际 | 差异 |
| --- | --- | --- |
| `StrategyComposer` 仅返回 `SignalCandidate` | 增加 `ComposerDecision` 持久化 | 扩展而非重构 |
| `BacktestOrchestrator` 直接调用 `runtime.on_bar` | 通过 `StrategyComposer` 聚合候选 | Phase 3 引入 Composer 层 |
| 无 `OrderIntent` | 引入 `OrderIntent` 桥接层 | Phase 3 新增 |
| 无 Golden Tests | G1-G4 覆盖核心场景 | Phase 3 引入 |
