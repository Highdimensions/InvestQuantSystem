# 回测平台执行模型

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案（Phase 1 实现后更新） |
| 适用范围 | 回测与量化研究平台 Phase 1-7 实施 |
| 相关文档 | [目标架构](./backtest-target-architecture.md)、[核心领域模型](./backtest-domain-model.md)、[数据契约](./backtest-data-contracts.md) |
| 最后更新 | 2026-07-03 |

---

## 1. 执行模型概述

### 1.1 两种执行模式

| 模式 | 说明 | 时钟 | 数据源 | 用途 |
| --- | --- | --- | --- | --- |
| Backtest | 离线回测 | `FrozenClock` | `MarketDataRepository` | 历史信号研究 |
| Historical Replay | 历史回放（复用核心） | `FrozenClock` | `MarketDataReplaySource` | 与实时影子对账 |
| Shadow Run | 实时影子运行 | `SystemClock` | `AKShareMarketDataSource` | 实时信号生成 |

**已确定**：三种模式共享 `FeatureEngine`、`StrategyRuntime`、`StrategyComposer`、`SignalService`、`SignalEvaluator`，不共享 `Clock`、`DataSource`、`FillModel`。

---

## 2. 事件排序规则

### 2.1 全局事件排序

所有事件按以下键排序后依次处理：

```
(primary_sort_key, secondary_sort_key)
primary_sort_key   = market_data_time       (UTC datetime)
secondary_sort_key = event_type_order      (int)
                      0 = corporate_action
                      1 = trading_status
                      2 = market_bar
                      3 = feature_update
                      4 = strategy_candidate
                      5 = composer_decision
                      6 = signal_event
                      7 = order_intent
                      8 = execution_validation
                      9 = portfolio_update
                     10 = evaluation_task
                     11 = portfolio_snapshot
```

**同一 market_data_time + 同一 event_type_order** 的多个事件按 **symbol 字母序**稳定排序。

**ADR-BT-005**：同一 `market_data_time` 的多个 symbol 按字母序作为三级排序键。

### 2.2 Bar 闭合检测

- 分钟级 Bar 在 `market_data_time = bar_end_time` 时立即闭合
- 午间休市（11:30-13:00）期间无新 Bar
- Bar Normalizer 拒绝 `is_closed=False` 的 Bar
- `BarNormalizer` 暂无午间虚拟事件注入（BT-TBD-04 待决策）

---

## 3. BacktestOrchestrator 执行流程

### 3.1 主循环

```
初始化
  ├─ 加载 RunSpec（from YAML 或 API）
  ├─ 校验配置（from_time < to_time，bindings 非空，Universe 可见）
  ├─ 解析 UniverseSnapshot（按 effective_time 选取）
  ├─ 冻结版本（resolved_config_hash）
  ├─ 初始化 Manifest（run_id，created_at）
  └─ 初始化每个 binding × symbol 的隔离状态

主循环（按 market_data_time 全局排序）
  for each market_data_time:
    ├─ VirtualClock.advance_to(market_data_time)
    ├─ 检查 Universe 是否切换（effective_time 到达）
    │
    ├─ for each binding_id:
    │    │
    │    ├─ for each symbol in binding's universe:
    │    │    ├─ 获取该 symbol 在当前 market_data_time 的 Bar
    │    │    ├─ FeatureEngine(binding_id, symbol).update_closed_bar(bar)
    │    │    ├─ StrategyRuntime(binding_id, symbol).on_bar(bar, snapshot)
    │    │    └─ → SignalCandidate
    │    │
    │    ├─ StrategyComposer(binding_id).resolve(candidates)
    │    ├─ → ComposerDecision（持久化）
    │    ├─ → SignalCandidate（胜者）
    │    │
    │    ├─ SignalService.create_event(candidate)
    │    ├─ → SignalEvent（持久化）
    │    ├─ OrderIntent.validate(intent)
    │    ├─ ExecutionEngine.apply(intent)
    │    │    ├─ MarketRulesEngine.check(intent)
    │    │    ├─ → OrderIntent（ACCEPTED / REJECTED）
    │    │    └─ PortfolioLedger.apply(accepted_intent)
    │    │         ├─ → PaperOrder + PaperFill
    │    │         └─ 更新持仓快照
    │    │
    │    └─ EvaluationScheduler.schedule(event)

后处理
  ├─ PortfolioEvaluator.compute_metrics(ledger)
  ├─ Reporter.generate_report(manifest)
  └─ Manifest.finalize(run_status, artifacts)
```

### 3.2 状态隔离

每个 `(binding_id, symbol)` 组合拥有：

```
FeatureEngine_instance   — 独立滚动窗口
StrategyRuntime_instance — 独立参数状态（frozen dataclass，无实例状态）
```

不同 `(binding_id, symbol)` 之间不共享上述实例。`MarketDataRepository` 在底层通过 symbol 隔离查询。

### 3.3 Universe 切换

当 `market_data_time >= next_universe.effective_time` 时：

```
触发 Universe 切换
  ├─ 记录 RunWarning(UNIVERSE_CHANGE)
  ├─ 停止对旧 universe 中已移除 symbol 的新信号生成
  ├─ 已有持仓不受影响（持仓不因 universe 变化而强制平仓）
  └─ 继续对新 universe 中 symbol 生成信号
```

---

## 4. 信号层与组合层交互

```
SignalEvent (from SignalService)
     │
     ├─ → SignalEvaluator ———— SignalEvaluation
     │                        (Signal Evaluation 回答方向预测能力)
     │
     └─ → BacktestOrchestrator
              ├─ OrderIntent 生成（from SignalEvent）
              ├─ ExecutionEngine 验证（MarketRulesEngine）
              ├─ PortfolioLedger.apply(OrderIntent)
              │    └─ PaperOrder + PaperFill
              └─ PortfolioEvaluator ———— PortfolioMetrics
                                    (Portfolio Backtest 回答可执行性)
```

**已确定**：信号层和组合层使用不同的输出模型，不得用一个字段同时输出两层结果。

---

## 5. 时间语义总结

| 阶段 | 时间键 | 说明 |
| --- | --- | --- |
| 行情接收到系统 | `ingest_time` | 系统时钟 |
| 行情市场时间 | `market_data_time` = `bar_end_time` | Bar 闭合时间 |
| 信号生成 | `event_time` | VirtualClock 当前时间 |
| 可执行时间 | `executable_time` | 下一个有效交易时段 |
| 成交时间 | `fill_time` | 按 FillModel 计算 |
| 评价时间 | `evaluation_time` | 按 EvaluationPolicy 计算 |

---

## 6. 错误处理

| 错误类型 | 处理方式 |
| --- | --- |
| 配置校验失败 | fail fast，不启动运行 |
| 数据缺失 | 记录 WARNING，继续处理可得的 bar |
| 信号校验失败 | 拒绝信号，记录警告 |
| 市场规则违反 | OrderIntent → REJECTED，不中断 |
| 存储写入失败 | 事务回滚，标记 run 失败 |
| Universe 不可见 | `UniverseUnavailableError`，拒绝运行 |

---

## 7. 与 Phase 0 文档的差异

| Phase 0 设计 | Phase 1 实现 | 差异说明 |
| --- | --- | --- |
| 事件排序含 12 种事件类型 | Phase 1 仅实现 Bar → Feature → Strategy → Signal 核心链路 | Phase 2 扩展到完整 12 种 |
| `VirtualClock` | `FrozenClock` 复用 | Phase 2 扩展 |
| `ExecutionEngine` | `OrderIntent` 生成（无执行验证） | Phase 4 完整实现 |
| `PortfolioLedger` | `PortfolioLedger` 接口（无实现） | Phase 4 完整实现 |
| `ComposerDecision` 持久化 | `ComposerDecision` 生成（无持久化） | Phase 3 完整实现 |
