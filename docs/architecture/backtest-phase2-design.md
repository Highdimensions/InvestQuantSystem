# Phase 2 架构设计补充

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 2 实施 |
| 相关文档 | [执行模型](./backtest-execution-model.md)、[核心领域模型](./backtest-domain-model.md) |
| 最后更新 | 2026-07-03 |

---

## 1. VirtualClock 扩展

### 1.1 动机

`FrozenClock` 只能做简单的 `advance(delta)`，不支持按目标时间跳转，也不记录时间序列历史。`VirtualClock` 在此基础上增加：

- `advance_to(target)`：直接跳转到目标时间（仅允许正向）
- `_history`：已访问时间点序列（用于确定性验证）

### 1.2 与 TradingCalendar 的交互

```
VirtualClock.advance_to(target_time)
  ├─ TradingCalendar.next_session_time(target_time) → 可能跳到下一个交易日
  └─ self.current_time = adjusted_time
```

**关键约束**：跨非交易时段（如午间休市、节假日）时，`VirtualClock` 仍然可以推进到任意目标时间，`TradingCalendar` 仅在 `next_evaluation_time` 中用于计算评价时间窗口。

---

## 2. BacktestScheduler 事件排序

### 2.1 排序规则（ADR-BT-005 实施）

```
事件优先级：
  0 = corporate_action
  1 = trading_status
  2 = market_bar          ← 核心输入
  3 = feature_update       ← 由 bar 触发
  4 = strategy_candidate   ← 由 feature_update 触发
  5 = composer_decision    ← Phase 3
  6 = signal_event        ← Phase 3
```

**Phase 2** 仅处理优先级 2（market_bar）和优先级 4（strategy_candidate）之间的事件序列。

### 2.2 稳定排序

同一 `market_data_time` 的多 symbol 按 **symbol 字母序** 排序（Python 默认字典序）。

### 2.3 乱序 Bar 处理

若 `incoming_bar.market_data_time < self._last_time`，记录 `OUT_OF_ORDER_BAR` 警告，回调时间已到，直接处理该 Bar（不回退）。

---

## 3. StatePartition 隔离设计

### 3.1 状态槽位

```
(binding_id, symbol) → {
    "feature_engine": RollingFeatureEngine,
    "strategy_runtime": StrategyRuntime,
    "bars": list[MarketBar],      # 仅调试用
}
```

### 3.2 实例化策略

```
for binding_id in spec.strategy_bindings:
    universe = resolver.resolve(binding_id.universe_id, at_time=spec.from_time)
    for symbol in universe.symbols:
        state_partition.get_or_create(binding_id, symbol)
            ├─ RollingFeatureEngine(lookback=3)
            └─ RuleStrategyRuntime.from_params(binding.params)
```

### 3.3 FeatureEngine 隔离验证

每个 `(binding_id, symbol)` 独立实例，共享同一个 `MarketDataRepository` 底层查询，不共享特征状态。

---

## 4. BacktestOrchestrator 主循环

### 4.1 核心循环（Phase 2 最小闭环）

```
1. 初始化 StatePartition（binding × symbol）
2. VirtualClock.advance_to(spec.from_time)
3. 加载 MarketDataRepository（spec.from_time → spec.to_time）
4. 获取排序后的 bar 序列（按 market_data_time）

for each bar in sorted_bars:
    5. VirtualClock.advance_to(bar.market_data_time)
    6. MarketDataRepository.save_bar(bar)
    7. StatePartition 检查 Universe 切换

    for each binding_id:
        if symbol not in binding's universe:
            continue
        state = StatePartition.get(binding_id, symbol)
        snapshot = state.feature_engine.update_closed_bar(bar)
        candidate = state.strategy_runtime.on_bar(bar, snapshot)
        if candidate is None:
            continue
        signal = SignalService.create_event(candidate)
        SignalRepository.append_signal(signal)
        记录统计（bars_processed, signals_generated）
```

### 4.2 Phase 2 不包含（留 Phase 3-4）

- ComposerDecision 持久化（Phase 3）
- OrderIntent 生成（Phase 3）
- MarketRulesEngine（Phase 4）
- PortfolioLedger（Phase 4）
- 多策略冲突解决（Phase 3）

---

## 5. BacktestRunResult

### 5.1 用途

Phase 2 的运行结果类，包含最小可用的统计信息，供 Phase 3+ 扩展使用。

### 5.2 字段

```python
@dataclass(frozen=True, slots=True)
class BacktestRunResult:
    run_id: str
    spec_hash: str
    total_bars: int
    bars_by_symbol: dict[str, int]
    signals: tuple[SignalEvent, ...]
    signal_count: int
    skipped_bars: int
    universe_changes: tuple[UniverseChangeEvent, ...]
    warnings: tuple[RunWarning, ...]
    started_at: datetime
    finished_at: datetime
```

---

## 6. 确定性保证

### 6.1 确定性要素

Phase 2 确保以下要素决定最终结果：

- 输入 Bar 序列（`MarketBar` 的 5 元组主键）
- 排序规则（`market_data_time` + symbol 字母序）
- 策略版本（`strategy_version` + `parameter_hash` + `code_version`）
- 特征版本（`feature_version`）
- 虚拟时钟（`FrozenClock` 或 `VirtualClock`）

### 6.2 确定性测试

相同输入运行两次，结果必须完全一致（`signal_ids` 相同）。

---

## 7. 与 Phase 1 设计文档的差异

| Phase 1 设计 | Phase 2 实际 | 差异 |
| --- | --- | --- |
| 完整 12 种事件类型 | Phase 2 仅处理 market_bar → signal 核心链路 | Phase 2 是 Phase 1 的子集 |
| `VirtualClock` | `VirtualClock` 在 `FrozenClock` 基础上扩展 | 实现方式具体化 |
| `ExecutionEngine` | Phase 4 | 范围缩小 |
| `ComposerDecision` 持久化 | Phase 3 | 范围缩小 |
| `PortfolioLedger` | Phase 4 | 范围缩小 |
