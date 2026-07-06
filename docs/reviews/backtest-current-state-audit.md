# 回测系统当前状态审计报告

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | Phase 0 交付物 |
| 审计日期 | 2026-07-03 |
| 审计范围 | 回测、策略、特征、信号、评价、组合、报告、测试 |
| 审计方法 | 代码只读审计 + 文档交叉验证 |
| 测试基线 | 85 passed / 0 failed |

---

## 1. 当前实际调用链

### 1.1 回测调用链（从代码推导）

```
用户入口（CLI/Dashboard/测试）
  ↓
BacktestRunner.run_bars(list[MarketBar])
  ├─ sorted(bars, key=market_data_time)     ← 全局排序，不区分 symbol
  ├─ feature_engine.update_closed_bar(bar)   ← 单 RollingFeatureEngine 实例
  ├─ composer.on_bar(bar, snapshot)         ← StrategyComposer 或单 StrategyRuntime
  │    └─ runtime.on_bar(bar, snapshot)     ← RuleStrategyRuntime / MomentumV1Strategy
  │         └─ SignalCandidate | None
  ├─ signal_service.create_event(candidate)  ← 补齐 executable_time、executable_price
  └─ signal_repository.append_signal(event) ← InMemorySignalRepository
       ↓
BacktestResult(bars_seen, signals_created, signal_ids)
  ↓ (外部)
SignalEvaluator.evaluate(task)
  ├─ signal_repository.get_signal(signal_id)
  ├─ market_repository.read_bars(...)        ← 读取 executable_time → due_time 路径
  ├─ fill_model.fill(signal, path)
  ├─ cost_model.cost_rate(direction)
  └─ 计算 raw_return, direction_return, net_return, MFE, MAE
       ↓
PaperPortfolio.apply_signal(signal, fill_price)
  ├─ PaperOrder + PaperFill
  └─ 更新 _positions, _fills
       ↓
EvaluationReportBuilder.build(evaluations)
```

### 1.2 时钟调用链（从代码推导）

```
FrozenClock / SystemClock
  ├─ clock.now() → datetime
  ├─ clock.market_now()
  └─ frozen_clock.advance(delta)
```

### 1.3 数据源调用链（从代码推导）

```
AKShareMarketDataSource.read(symbols, from_time, to_time)
  ├─ _fetch_rows(client, symbol, from_time, to_time)
  ├─ _akshare_symbol(symbol)  ← 交易所前缀转换
  └─ BarNormalizer.normalize_raw_bar()
       ├─ field_map 应用
       ├─ 时间字段 UTC 规范化
       └─ MarketBar(schema_version="market-bar-v1")
            ↓
MarketDataRepository.save_bar(bar)
  ├─ 重复检测（5 元组主键）
  ├─ 内容指纹比对（VersionConflictError / quarantine）
  └─ _bars[key] = bar
```

### 1.4 评价调度调用链（从代码推导）

```
EvaluationScheduler
  ├─ find_due_tasks(now, policy_version)
  │    └─ signal_repository.find_unevaluated(signal_id, horizon, policy_version)
  ├─ claim(task_key, worker_id, lease_seconds)
  │    └─ UPDATE EvaluationTask SET claimed_at, lease_expires_at, worker_id
  └─ (外部) signal_evaluator.evaluate(task)
       └─ signal_repository.upsert_evaluation(evaluation)
```

---

## 2. 当前模块边界

### 2.1 清晰边界

| 模块 | 状态 | 评估 |
| --- | --- | --- |
| `contracts/` | 已确定 | 定义不可变数据类；无外部依赖；完全隔离 |
| `time/` | 已确定 | `Clock` Protocol + `FrozenClock`/`SystemClock`；日历抽象 |
| `market_data/` | 已确定 | Source/Repository/Quarantine/Replay 分层清晰 |
| `features/` | 已确定 | 纯计算层；`RollingFeatureEngine.update_closed_bar` |
| `strategies/` | 已确定 | `StrategyRuntime` Protocol；`RuleStrategyRuntime`/`MomentumV1Strategy` |
| `signals/` | 已确定 | `SignalService` 校验 + `InMemorySignalRepository` 持久化 |
| `evaluation/` | 已确定 | Evaluator + Scheduler + CostModel + FillModel |
| `reporting/` | 部分 | 仅 `EvaluationReportBuilder` 简单聚合；`ShadowRunComparator` |
| `config/` | 已确定 | `VersionRegistry` + `DataSourceProfile` |

### 2.2 边界问题

| 问题 | 位置 | 严重性 | 说明 |
| --- | --- | --- | --- |
| 外部依赖注入缺失 | `BacktestRunner` | 中 | 依赖 `RollingFeatureEngine`/`SignalService`/`SignalRepository` 注入，但没有端口抽象 |
| CLI 入口缺失 | `cli/` | 高 | `PLANS.md` 规划了 `cli/replay.py` 等，但目录不存在 |
| Dashboard 与核心紧耦合 | `dashboard/` | 低 | Dashboard 通过 `InMemoryMarketDataRepository` 注入；但不影响回测链路 |

---

## 3. 当前单策略能力

| 能力 | 状态 | 代码位置 |
| --- | --- | --- |
| 单策略 `BacktestRunner` | ✅ 已实现 | `backtest/runner.py:46-70` |
| 按 `market_data_time` 排序驱动 | ✅ 已实现 | `backtest/runner.py:59` |
| 拒绝未闭合 Bar | ✅ 已实现 | `RuleStrategyRuntime.on_bar` 调用 `bar.validate(require_closed=True)` |
| 输出 `BacktestResult` | ✅ 已实现 | 仅含 `bars_seen, signals_created, signal_ids` |
| `RuleStrategyRuntime` 3 条规则 | ✅ 已实现 | `strategies/runtime.py:88-138` |
| 策略参数可配置 | ✅ 已实现 | `ParamSchema` + `from_params` |
| 参数 Hash | ✅ 已实现 | `compute_parameter_hash` (SHA-256) |
| 参数范围校验 | ❌ 缺失 | 负 `breakout_volume_ratio` 可通过 `from_params` 传入 |
| 报告自动生成 | ❌ 缺失 | 南大光电报告为手工编写 |

---

## 4. 当前多策略组合能力

| 能力 | 状态 | 代码位置 |
| --- | --- | --- |
| `StrategyComposer` 框架 | ✅ 已实现 | `strategies/composer.py` |
| 3 种冲突策略 | ✅ 已实现 | `PRIORITY_MAX_CONFIDENCE / UNANIMOUS / SCORE_WEIGHTED` |
| 方向冲突弃发 | ✅ 已实现 | `_resolve_priority_max_confidence` |
| 候选者 `reason_codes` 合并 | ✅ 已实现 | 写入胜者的 `reason_codes` |
| `ComposerConflictRecord` | ✅ 已实现 | 仅在函数内返回后丢弃 |
| 冲突记录持久化 | ❌ 缺失 | `_record_conflict()` 返回值无调用方消费 |
| 按 strategy_version 分桶 | ❌ 缺失 | Composer 输出只有合并后的单一 `signal_id` |
| 多策略回测报告 | ❌ 缺失 | 无对应生成器 |

---

## 5. 当前多股票能力

| 能力 | 状态 | 代码位置 | 说明 |
| --- | --- | --- | --- |
| 多 symbol `MarketBar` 输入 | ⚠️ 受限 | `backtest/runner.py:59` | 按全局 `market_data_time` 排序，不区分 symbol |
| FeatureEngine 按 symbol 隔离 | ✅ 已实现 | `features/engine.py` | `_bars_by_symbol: dict[str, list[MarketBar]]` |
| Repository 按 symbol 查询 | ✅ 已实现 | `market_data/repository.py` | 5 元组主键第一维为 symbol |
| `AKShareMarketDataSource` 批量读取 | ✅ 已实现 | `market_data/akshare_source.py` | `read(symbols: Sequence[str], ...)` |
| 多 symbol 回测隔离 | ❌ 有风险 | `features/engine.py` | 单 `RollingFeatureEngine` 实例；若同策略实例跨 symbol 调用 `update_closed_bar`，特征状态会被覆盖 |

**从代码推导的隔离缺陷**：若外部用单 `RollingFeatureEngine` 实例依次调用不同 symbol 的 Bar（交替输入），特征引擎的 `_bars_by_symbol` 虽按 symbol 隔离字典槽位，但每 symbol 的滚动窗口（MA 窗口等）**在各自的 symbol 槽位内是独立的**，不会跨 symbol 污染。真正的风险是：当同一 `RuleStrategyRuntime` 实例对 symbol A 产生信号后，再用同样实例处理 symbol B 的 Bar——此时 `RuleStrategyRuntime` 本身是无状态的（frozen dataclass），但如果策略内部有任何实例级滚动状态（当前没有），才可能有问题。

结论：多 symbol 回测**从代码推导**是可行的，FeatureEngine 和 Repository 均正确隔离。风险在于当前 `BacktestRunner` 的 `run_bars` 对混合 symbol 的 Bar 列表执行全局排序——不同 symbol 的 Bar 交替出现时，FeatureEngine 不会混淆（symbol key 隔离），但策略输出的信号 `event_time` 可能产生歧义（多 symbol 同时闭合同一分钟的情况）。

---

## 6. 当前股票池能力

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `Universe` / `StockPool` 一等公民 | ❌ 缺失 | 仓库中无此概念 |
| 策略适用股票池配置 | ❌ 缺失 | `StrategySpec` 无 universe 字段 |
| 指数成分 as-of 约束 | ⚠️ 基础 | `AsOfDataset` 已定义但未用于股票池 |
| 股票池版本化 | ❌ 缺失 | 无对应模块 |
| 股票池变更事件 | ❌ 缺失 | 无对应触发逻辑 |

**结论**：股票池能力**完全缺失**。当前要跑多股票只能通过传入混合 symbol 的 Bar 列表，或在策略 `on_bar` 内部硬编码 `if bar.symbol not in MY_UNIVERSE: return None`，这违反了「策略核心只依赖内部契约」的边界。

---

## 7. 当前信号评价能力

| 能力 | 状态 | 代码位置 | 说明 |
| --- | --- | --- | --- |
| 固定窗口评价 | ✅ 已实现 | `evaluation/evaluator.py:38-88` | `raw_return, direction_return, net_return` |
| MFE / MAE | ✅ 已实现 | `evaluation/evaluator.py:61-72` | 按方向取 max/min |
| `UNEXECUTABLE` 样本处理 | ✅ 已实现 | `_unexecutable` 方法 |
| `POSTPONED` 状态 | ✅ 已实现 | `_unavailable` 方法 |
| 成本模型 | ✅ 已实现 | `FixedBpsCostModel` |
| 成交模型 | ✅ 已实现 | `NextBarOpenFillModel` |
| 三重障碍 | ⚠️ 基础 | 有字段 `triple_barrier_label` 但未激活 |
| 置信度校准 | ❌ 缺失 | 无对应聚合 |
| 多维分桶 | ❌ 缺失 | `EvaluationReportBuilder` 只统计 status 和 policy_version |
| 按 symbol 分桶 | ❌ 缺失 | 评价链路未使用 symbol 字段分组 |
| 按 reason_code 分桶 | ❌ 缺失 | 同上 |
| 按年份/月份分桶 | ❌ 缺失 | 同上 |

---

## 8. 当前模拟持仓能力

| 能力 | 状态 | 代码位置 | 说明 |
| --- | --- | --- | --- |
| 状态机 | ✅ 基础 | `portfolio/paper.py:22-83` | 空仓/持仓，仅 0%/100% 仓位 |
| T+1 约束 | ❌ 缺失 | `portfolio/paper.py` | 无当日买入不可卖建模 |
| 整数手 | ❌ 缺失 | 无 `default_quantity` 以外的整数约束 |
| 涨跌停阻断 | ⚠️ 基础 | `ExecutionStatus.UNEXECUTABLE` 有枚举，但 `NextBarOpenFillModel` 未实现 |
| Stop / 止盈止损 | ❌ 缺失 | 无主动止损触发逻辑 |
| realized_pnl | ⚠️ 基础 | 有字段但始终为 `Decimal("0")` |
| unrealized_pnl | ⚠️ 基础 | 有字段但始终为 `Decimal("0")` |
| 多 symbol 并行持仓 | ⚠️ 基础 | `_positions: dict[str, Decimal]` 支持多 symbol，但无仓位限制 |
| 现金管理 | ❌ 缺失 | 无资金余额概念；每次按 `default_quantity` 成交 |

---

## 9. 当前报告能力

| 能力 | 状态 | 代码位置 | 说明 |
| --- | --- | --- | --- |
| `EvaluationReportBuilder` | ⚠️ 基础 | `reporting/reports.py:30-36` | 仅输出 `total, status_counts, version_counts` |
| 多维分桶报告 | ❌ 缺失 | 无 | |
| Markdown 报告 | ⚠️ 基础 | 仅简单模板 | |
| HTML/Dashboard 报告 | ❌ 缺失 | Dashboard 只有 API，无报告生成 | |
| 组合层报告 | ❌ 缺失 | 无 | |
| 自动报告生成 | ❌ 缺失 | 南大光电报告为手工编写 | |

**从代码推导**：报告能力严重不足。南大光电报告中的「按方向/原因/年份分桶」「命中率」「平均/中位方向收益」「MFE/MAE」等指标**不是代码生成的**。

---

## 10. 当前持久化和版本治理

### 10.1 版本键设计

| 对象 | 版本键 | 状态 | 说明 |
| --- | --- | --- | --- |
| `MarketBar` | 5 元组 | ✅ 完整 | `(symbol, timeframe, market_data_time, data_source_version, as_of_version)` |
| `SignalEvent` | `signal_id` | ✅ 完整 | 事件内容哈希 |
| `SignalEvaluation` | 8 元组 | ✅ 完整 | `signal_id + horizon + evaluator + policy + cost + fill + data + as_of` |
| `FeatureSnapshot` | `feature_snapshot_id` | ✅ 完整 | 含输入范围哈希 |
| `StrategyVersion` | `identity_key` | ✅ 完整 | `(name, version, code_version, parameter_hash)` |
| `PaperOrder/Fill` | `paper_run_id + signal_id` | ✅ 完整 | 确定性哈希 |
| BacktestRun | ❌ 缺失 | 无 | 无 `run_id` / `run_manifest` |
| Universe | ❌ 缺失 | 无版本化 | |
| 策略绑定 | ❌ 缺失 | 无版本化 | |
| Market Rules | ❌ 缺失 | 无版本化 | |

### 10.2 持久化实现

| 组件 | 实现 | 说明 |
| --- | --- | --- |
| 市场数据 | `InMemoryMarketDataRepository` + `SQLiteMarketDataRepository` | 两者接口一致 |
| 信号与评价 | `InMemorySignalRepository` + `SQLiteSignalRepository` | 两者接口一致 |
| 版本注册 | `VersionRegistry` (进程内存) | **非 frozen，含可变字典；无锁保护** |
| Backtest 结果 | ❌ 缺失 | 无序列化输出 |
| Manifest | ❌ 缺失 | 无 |

### 10.3 关键风险

| 风险 | 严重性 | 说明 |
| --- | --- | --- |
| `VersionRegistry._frozen_strategies` 无锁 | 高 | 多线程并发调用 `freeze_strategy` 有竞态 |
| `DEFAULT_REGISTRY` 全局单例 | 高 | 跨测试状态泄漏 |
| Backtest 无 Manifest | 高 | 运行结果不可追溯 |
| Backtest 无版本键 | 高 | 无法与其他运行比较 |

---

## 11. 当前测试覆盖

### 11.1 测试现状

| 测试目录 | 文件数 | 框架 | 覆盖内容 |
| --- | --- | --- | --- |
| `tests/unit/` | 4 | pytest | SQLite 仓库、时钟日历、AKShare 源、数据对账 |
| `tests/contract/` | 1 | pytest | 数据契约验证 |
| `tests/integration/` | 3 | pytest | 研究流水线、策略插件、Dashboard API |
| `tests/strategies/` | 4 | pytest | Composer 冲突、注册、动量、协议 |

**总计：85 passed, 0 failed**

### 11.2 缺失测试

| 场景 | 状态 | 说明 |
| --- | --- | --- |
| 多股票回测 | ❌ 无 | 所有测试仅用 `000001` |
| 多策略组合 + 多股票 | ❌ 无 | 仅单策略或单股票 |
| BacktestRunner 单元测试 | ❌ 无 | 无直接测试 |
| 报告自动生成测试 | ❌ 无 | `EvaluationReportBuilder` 无测试 |
| 属性测试（随机输入） | ⚠️ 基础 | 仅参数哈希稳定性 |
| Golden Tests（价格路径） | ⚠️ 基础 | 仅数据对账 |
| 故障恢复测试 | ⚠️ 基础 | `evaluation-recovery` 目标存在但场景不完整 |
| T+1 建模测试 | ❌ 无 | 无 |
| 涨跌停测试 | ❌ 无 | 无 |
| 并发安全测试 | ❌ 无 | 无 |
| 确定性与可复现测试 | ❌ 无 | 无 |
| Fuzz 测试 | ❌ 无 | 无 |

---

## 12. 性能与资源使用

| 维度 | 当前状态 | 说明 |
| --- | --- | --- |
| 并行处理 | ❌ 无 | 单线程顺序处理 Bar |
| 多 symbol 扩展 | ⚠️ 受限 | 串行 `for symbol in symbols` |
| 内存 | ⚠️ 未知 | 无 Benchmark；`_bars_by_symbol` 可能无界增长 |
| 特征计算 | ✅ 轻量 | 纯 Python 计算，无外部依赖 |
| Repository 查询 | ⚠️ 未知 | InMemory 版本无索引优化 |
| 评价延迟 | ⚠️ 未知 | 无 Benchmark |
| bars/s 吞吐 | ⚠️ 未知 | 无 Benchmark |

---

## 13. 文档与代码不一致

| 编号 | 不一致位置 | 文档描述 | 代码实际 | 来源 |
| --- | --- | --- | --- | --- |
| INCONS-01 | `docs/architecture/module-design.md` | `BacktestRunner` 输出回测报告 | 仅输出 `BacktestResult`（signal_id 列表） | `backtest/runner.py` |
| INCONS-02 | `docs/architecture/module-design.md` | `Reporter` 模块 | 无独立 `Reporter` 类 | 不存在 |
| INCONS-03 | `PLANS.md` | `cli/replay.py`, `cli/evaluate.py` | 目录不存在 | 不存在 |
| INCONS-04 | `PLANS.md` | `tests/property/`, `tests/replay/`, `tests/recovery/` | 目录不存在 | 不存在 |
| INCONS-05 | `docs/architecture/module-design.md` | `Metrics and Reporting` 输出报告 | 仅 `EvaluationReportBuilder` 简单聚合 | `reporting/reports.py` |
| INCONS-06 | 南大光电报告 | 命中率、MFE/MAE 按维度分桶 | 代码不生成此报告 | 手工编写 |
| INCONS-07 | `docs/decisions/open-questions.md` TBD-18 | Tick 数据需求评估 | 无 Tick 数据处理能力 | 尚未决策 |
| INCONS-08 | `docs/architecture/testing-and-evaluation.md` | Walk-Forward 测试 | 无实现 | 尚未实现 |

---

## 14. 阻断机构级使用的问题

| 编号 | 问题 | 严重性 | 说明 |
| --- | --- | --- | --- |
| BLOCK-01 | 无 BacktestRun Manifest | P0 | 运行结果不可复现、无版本追踪 |
| BLOCK-02 | 无自动报告生成 | P0 | 无法批量输出多维分桶报告 |
| BLOCK-03 | 无 Universe/股票池概念 | P0 | 无法为不同策略配置不同股票池 |
| BLOCK-04 | 无 T+1 约束建模 | P0 | 模拟持仓结果不可信 |
| BLOCK-05 | `VersionRegistry` 无锁 | P1 | 多线程并发不安全 |
| BLOCK-06 | `DEFAULT_REGISTRY` 全局单例 | P1 | 跨测试状态泄漏 |
| BLOCK-07 | 无 ComposerDecision 持久化 | P1 | 多策略归因链路断裂 |
| BLOCK-08 | 无策略绑定（StrategyBinding） | P1 | 无法表达「策略 × 股票池 × 参数」绑定 |
| BLOCK-09 | 无 BacktestRunSpec | P1 | 无法从 YAML/JSON 加载配置并冻结 |
| BLOCK-10 | 无 A 股市场规则引擎 | P1 | 涨跌停、T+1、整数手均无建模 |
| BLOCK-11 | 无 Portfolio Ledger | P1 | 现金、资产守恒无法验证 |
| BLOCK-12 | 无 Fuzz / 属性测试 | P1 | 边界条件和随机输入无覆盖 |
| BLOCK-13 | 无 Benchmark 基线 | P2 | 性能目标无依据 |
| BLOCK-14 | 无故障恢复测试 | P2 | 中断场景无验证 |
| BLOCK-15 | 无一致性测试 | P2 | 实时与回放无可验证一致性 |

---

## 15. 已存在能力（不应重复建设）

| 能力 | 位置 | 状态 | 说明 |
| --- | --- | --- | --- |
| `MarketBar` 不可变 + 5 元组主键 | `contracts/market.py` | ✅ 完整 | 不应重写 |
| `SignalEvent` append-only | `signals/service.py` + `signals/repository.py` | ✅ 完整 | 不应重写 |
| `FeatureSnapshot` 版本化 | `features/engine.py` | ✅ 完整 | 不应重写 |
| `RollingFeatureEngine` 按 symbol 隔离 | `features/engine.py` | ✅ 正确 | 不应重写 |
| `AsOfDataset` as-of 语义 | `contracts/reference_data.py` | ✅ 完整 | 可复用 |
| `StrategyRuntime` Protocol | `strategies/protocol.py` | ✅ 完整 | 不应重写 |
| `ParamSchema` 参数校验 | `strategies/schema.py` | ✅ 完整 | 不应重写 |
| `compute_parameter_hash` | `strategies/schema.py` | ✅ 完整 | 不应重写 |
| `StrategyComposer` 冲突策略 | `strategies/composer.py` | ✅ 完整 | 应扩展，不重写 |
| `SignalEvaluator` 指标计算 | `evaluation/evaluator.py` | ✅ 基础 | 应扩展，不重写 |
| `CostModel` / `FillModel` | `evaluation/cost_model.py`, `fill_model.py` | ✅ 基础 | 应扩展，不重写 |
| `Clock` 抽象 (`FrozenClock`) | `time/clock.py` | ✅ 完整 | 不应重写 |
| `TradingCalendar` 抽象 | `time/trading_calendar.py` | ✅ 基础 | 应扩展，不重写 |
| `MarketDataRepository` 版本化 | `market_data/repository.py` | ✅ 完整 | 不应重写 |
| `MarketDataReplaySource` | `market_data/replay.py` | ✅ 基础 | 应扩展，不重写 |
| `Quarantine` 异常隔离 | `market_data/quarantine.py` | ✅ 完整 | 不应重写 |
| `VersionRegistry` 冻结 | `config/versions.py` | ⚠️ 基础 | 应加锁，不重写 |
| 测试框架 (pytest) | `pyproject.toml` | ✅ 就绪 | 不应替换 |
| Ruff linting | `requirements.txt` | ✅ 就绪 | 不应替换 |

---

## 16. 汇总：能力矩阵

| 能力域 | 完整 | 基础 | 缺失 | 阻断 |
| --- | --- | --- | --- | --- |
| 单策略回测 | 6 | 1 | 1 | 1 |
| 多策略组合 | 5 | 1 | 3 | 1 |
| 多股票支持 | 3 | 1 | 2 | 1 |
| 股票池 | 0 | 1 | 3 | 1 |
| 信号评价 | 4 | 3 | 5 | 0 |
| 模拟持仓 | 2 | 4 | 5 | 1 |
| 报告生成 | 0 | 2 | 5 | 1 |
| 持久化/版本 | 6 | 1 | 4 | 1 |
| 测试覆盖 | 3 | 4 | 12 | 0 |
| 可观测性 | 1 | 2 | 8 | 0 |
| **总计** | **30** | **20** | **48** | **8** |

---

## 17. 结论

Phase 0 审计完成。当前系统在**单策略回测、数据契约、FeatureEngine、版本化存储和基础评价链路**上已有扎实基础，但距离机构级回测平台存在显著差距：

1. **事实层缺口**：无 `BacktestRunSpec`、`BacktestRunManifest`、`Universe`、`StrategyBinding`、`ComposerDecision` 持久化。
2. **执行层缺口**：无 T+1、涨跌停、整数手、市场规则引擎；`PaperPortfolio` 仅为基础桩。
3. **报告层缺口**：无自动报告生成；`EvaluationReportBuilder` 严重不足。
4. **治理层缺口**：`VersionRegistry` 无锁、`DEFAULT_REGISTRY` 全局单例、无确定性测试。
5. **文档层缺口**：多处文档规划与代码实现不一致（`cli/`, `tests/property/` 等）。

**Phase 1 应优先落地**：`BacktestRunSpec` + `Universe` + `StrategyBinding` 契约，作为后续所有能力的地基。
