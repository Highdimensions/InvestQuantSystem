# 回测平台可观测性

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 1-7 实施 |
| 相关文档 | [当前状态审计](../reviews/backtest-current-state-audit.md)、[目标架构](./backtest-target-architecture.md) |
| 最后更新 | 2026-07-03 |

---

## 1. 可观测性目标

即使当前是离线回测，也必须具备完整诊断能力。回测失败或结果异常时，必须能在分钟内定位问题。

---

## 2. 结构化日志

### 2.1 日志字段规范

每条日志必须包含以下字段：

| 字段 | 类型 | 说明 | 来源 |
| --- | --- | --- | --- |
| `timestamp` | datetime | UTC 时间 | 自动 |
| `level` | string | DEBUG/INFO/WARN/ERROR | 自动 |
| `run_id` | string | 所属回测运行 | 运行时注入 |
| `binding_id` | string | 策略绑定 ID | 回测上下文 |
| `symbol` | string | 标的代码 | 回测上下文 |
| `market_data_time` | datetime | 行情市场时间 | 事件上下文 |
| `event_sequence` | int | 该 bar 内的事件序号 | 运行时递增 |
| `current_virtual_time` | datetime | 虚拟时钟当前时间 | 调度器 |
| `source_data_partition` | string | 原始数据分区 | 数据加载时注入 |
| `strategy_version` | string | 策略版本 | 绑定上下文 |
| `data_version` | string | 数据源版本 | 绑定上下文 |
| `warning_code` | string | 警告代码 | 代码产生 |
| `error_category` | string | 错误分类 | 代码产生 |

### 2.2 警告代码

| 代码 | 说明 | 严重性 | 触发条件 |
| --- | --- | --- | --- |
| `MISSING_BAR` | 预期 bar 缺失 | warn | 连续 bar 时间间隔超过预期 |
| `DUPLICATE_BAR` | 重复 bar | info | 同一 market_data_time 的第二个 bar |
| `OUT_OF_ORDER_BAR` | 乱序 bar | warn | bar.market_data_time < 上一个 bar |
| `QUARANTINE_RECORD` | 数据进入隔离区 | warn | 规范化失败或版本冲突 |
| `UNIVERSE_CHANGE` | 股票池成分变化 | info | effective_time 到达，symbols 变化 |
| `SIGNAL_REJECTED` | 信号被 Composer 拒绝 | info | direction conflict + abstained |
| `ORDER_REJECTED` | 订单被市场规则拒绝 | info | 涨跌停/停牌/T+1/资金不足 |
| `EVALUATION_POSTPONED` | 评价任务延期 | warn | 行情暂不可用 |
| `DATA_INTERRUPTION` | 数据源中断 | error | N 个连续 bar 缺失 |
| `VERSION_MISMATCH` | 版本不一致 | error | 检测到混合版本 |
| `DETERMINISM_VIOLATION` | 确定性违规 | error | 相同输入产生不同结果 |

---

## 3. Metrics

### 3.1 处理指标

| 指标名 | 类型 | 标签 | 说明 |
| --- | --- | --- | --- |
| `backtest_bars_processed_total` | Counter | `run_id`, `symbol`, `timeframe` | 已处理的 bar 总数 |
| `backtest_bars_skipped_total` | Counter | `run_id`, `symbol`, `reason` | 跳过的 bar 总数 |
| `backtest_duplicate_bars_total` | Counter | `run_id`, `symbol` | 重复 bar 总数 |
| `backtest_out_of_order_bars_total` | Counter | `run_id`, `symbol` | 乱序 bar 总数 |
| `backtest_missing_bars_total` | Counter | `run_id`, `symbol` | 缺失 bar 总数 |

### 3.2 信号指标

| 指标名 | 类型 | 标签 | 说明 |
| --- | --- | --- | --- |
| `backtest_signals_generated_total` | Counter | `run_id`, `binding_id`, `symbol`, `direction` | 生成的信号总数 |
| `backtest_signals_rejected_total` | Counter | `run_id`, `binding_id`, `symbol`, `rejection_reason` | 被拒绝的信号总数 |
| `backtest_conflicts_total` | Counter | `run_id`, `binding_id`, `policy`, `decision` | 组合冲突总数 |
| `backtest_abstained_total` | Counter | `run_id`, `binding_id`, `reason` | 弃发信号总数 |

### 3.3 执行指标

| 指标名 | 类型 | 标签 | 说明 |
| --- | --- | --- | --- |
| `backtest_orders_total` | Counter | `run_id`, `portfolio_id`, `side`, `status` | 订单总数（按状态） |
| `backtest_orders_accepted_total` | Counter | `run_id`, `portfolio_id`, `symbol` | 接受订单数 |
| `backtest_orders_rejected_total` | Counter | `run_id`, `portfolio_id`, `reason` | 拒绝订单数 |
| `backtest_fills_total` | Counter | `run_id`, `portfolio_id`, `symbol`, `side` | 成交总数 |
| `backtest_t_plus_1_blocked_total` | Counter | `run_id`, `portfolio_id`, `symbol` | T+1 阻断数 |
| `backtest_limit_blocked_total` | Counter | `run_id`, `portfolio_id`, `symbol`, `limit_direction` | 涨跌停阻断数 |
| `backtest_suspended_blocked_total` | Counter | `run_id`, `portfolio_id`, `symbol` | 停牌阻断数 |

### 3.4 评价指标

| 指标名 | 类型 | 标签 | 说明 |
| --- | --- | --- | --- |
| `backtest_evaluations_completed_total` | Counter | `run_id`, `binding_id`, `horizon` | 已完成评价数 |
| `backtest_evaluations_postponed_total` | Counter | `run_id`, `binding_id`, `horizon` | 延期评价数 |
| `backtest_evaluation_backlog` | Gauge | `run_id`, `horizon` | 当前积压评价任务数 |
| `backtest_oldest_evaluation_age_seconds` | Gauge | `run_id`, `horizon` | 最老未完成评价的年龄 |

### 3.5 性能指标

| 指标名 | 类型 | 标签 | 说明 |
| --- | --- | --- | --- |
| `backtest_report_duration_seconds` | Histogram | `run_id`, `report_type` | 报告生成耗时 |
| `backtest_total_runtime_seconds` | Gauge | `run_id` | 总运行时间 |
| `backtest_peak_memory_mb` | Gauge | `run_id` | 峰值内存 |
| `backtest_processed_per_second` | Gauge | `run_id` | bar/s 处理速率 |

### 3.6 阈值说明

**已确定**：以上阈值在 Phase 1-7 实施中均标记为**待基准测试确定**，不得使用未经实证的阈值。每条告警在阈值确定前记录为 `TBD`。

---

## 4. 调试模式

### 4.1 事件链路导出

回测运行结束后，应支持针对以下维度导出完整事件链路：

```
run_id + binding_id + symbol + time_range
```

导出格式：

```json
{
  "run_id": "abc123",
  "binding_id": "vol_breakout_hs300_v1",
  "symbol": "300346",
  "from_time": "2025-06-01T00:00:00Z",
  "to_time": "2025-06-05T00:00:00Z",
  "events": [
    {
      "event_sequence": 1,
      "event_type": "MarketBarClosed",
      "market_data_time": "2025-06-02T09:31:00Z",
      "bar": { "open": 42.0, "high": 42.5, "low": 41.8, "close": 42.2, "volume": 12345 }
    },
    {
      "event_sequence": 2,
      "event_type": "FeatureSnapshot",
      "features": { "return_1": 0.004, "volume_ratio": 1.8, "ma_distance": 0.01 }
    },
    {
      "event_sequence": 3,
      "event_type": "SignalCandidate",
      "strategy_name": "volume_breakout",
      "direction": 1,
      "score": "0.70",
      "confidence": "0.60"
    },
    {
      "event_sequence": 4,
      "event_type": "ComposerDecision",
      "decision": "WINNER_SELECTED",
      "winner": "volume_breakout"
    },
    {
      "event_sequence": 5,
      "event_type": "SignalEvent",
      "signal_id": "sig_xxx",
      "direction": 1
    },
    {
      "event_sequence": 6,
      "event_type": "OrderIntent",
      "intent_id": "ord_xxx",
      "status": "ACCEPTED",
      "fill_price": "42.20"
    },
    {
      "event_sequence": 7,
      "event_type": "PaperFill",
      "fill_id": "fill_xxx",
      "quantity": "100",
      "fee": "0.021"
    },
    {
      "event_sequence": 8,
      "event_type": "EvaluationTask",
      "task_id": "task_xxx",
      "horizon_seconds": 900,
      "due_time": "2025-06-02T09:46:00Z"
    }
  ]
}
```

### 4.2 调试开关

```python
@dataclass
class BacktestDebugConfig:
    dump_event_chain: bool = False          # 导出完整事件链路
    dump_feature_snapshots: bool = False    # 导出所有特征快照
    dump_composer_decisions: bool = False   # 导出所有 ComposerDecision
    dump_order_intents: bool = False       # 导出所有 OrderIntent（含拒绝）
    verbose_logging: bool = False           # 每 bar 打印摘要
    stop_on_first_warning: bool = False    # 第一个警告时停止（调试用）
    stop_on_first_error: bool = True       # 第一个错误时停止
```

---

## 5. 告警规则

### 5.1 告警分级

| 等级 | 条件 | 响应 | 是否暂停结果解释 |
| --- | --- | --- | --- |
| P1 | `backtest_bars_missing_total > TBD` 且持续超过 TBD 分钟 | 立即处理 | 是（受影响 run） |
| P1 | `backtest_evaluation_backlog` 超过 TBD 且持续增加 | 立即处理 | 是（积压期间） |
| P1 | `DETERMINISM_VIOLATION` 出现 | 立即处理 | 是（该 run） |
| P2 | `backtest_quarantine_records_total` 超过 TBD | 当日排查 | 否（标记受影响数据） |
| P2 | `backtest_version_mismatch` 出现 | 当日排查 | 是（混合版本部分） |
| P2 | `backtest_signal_persist_failure_total > 0` | 当日排查 | 是（失败部分） |
| P3 | `backtest_report_duration_seconds > TBD` | 排期修复 | 否 |
| P3 | `backtest_orders_rejected_total` 占比超过 TBD | 排期修复 | 否 |

**已确定**：具体阈值待 Phase 7 基准测试后确定，不得在阈值未知时声称 P1/P2 告警已配置。

### 5.2 告警格式

每条告警必须包含：

- `run_id`
- `metric` 名称和当前值
- `threshold`（若已知）
- `duration`
- `affected_symbols`（若适用）
- `runbook_link`（指向 `docs/runbooks/` 中的对应 Runbook）
- `pause_interpretation`（布尔值）

---

## 6. 与现有可观测性的关系

| 现有设计 | 扩展点 |
| --- | --- |
| `docs/architecture/testing-and-evaluation.md` 第 8.1 节结构化日志字段 | 扩展：新增 `run_id`, `binding_id`, `event_sequence`, `current_virtual_time` |
| `docs/architecture/testing-and-evaluation.md` 第 8.2 节 Metrics | 扩展：新增 backtest 专用指标（处理/信号/执行/评价/性能） |
| `docs/architecture/testing-and-evaluation.md` 第 8.3 节告警分级 | 扩展：backtest 场景下的具体告警条件 |
| `docs/architecture/testing-and-evaluation.md` 第 8.4 节最小 runbook | 扩展：新增 backtest 专用 runbook |

---

## 7. Runbook 清单

Phase 6 完成时，至少应有以下 runbook：

| Runbook | 内容 |
| --- | --- |
| `docs/runbooks/run-backtest.md` | 如何运行一次回测（从 RunSpec 到报告） |
| `docs/runbooks/debug-backtest-mismatch.md` | 回测结果与预期不符时的排查步骤 |
| `docs/runbooks/recover-failed-backtest.md` | 回测中断后如何恢复 |
| `docs/runbooks/analyze-backtest-report.md` | 如何解读回测报告（区分信号层和组合层） |
| `docs/runbooks/debug-data-quality.md` | 行情数据质量问题排查 |
| `docs/runbooks/debug-signal-quality.md` | 信号质量问题排查 |
