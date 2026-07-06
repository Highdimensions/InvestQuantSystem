# Phase 5 架构设计补充：评价与报告

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 5 实施 |
| 相关文档 | [Phase 4 设计](./backtest-phase4-design.md)、[执行模型](./backtest-execution-model.md)、[核心领域模型](./backtest-domain-model.md) |
| 最后更新 | 2026-07-03 |

---

## 1. SignalMetrics（信号层指标）

### 1.1 分桶维度

按 `(strategy_name, strategy_version, symbol, direction, reason_code, year, month)` 分组。

### 1.2 聚合指标

| 指标 | 公式 |
| --- | --- |
| sample_count | 样本数 |
| win_rate | net_return > 0 的比例 |
| avg_net_return | 平均净收益 |
| std_net_return | 净收益标准差 |
| avg_mfe | 平均最大有利偏移 |
| avg_mae | 平均最大不利偏移 |
| mfe_mae_ratio | avg_mfe / abs(avg_mae) |

### 1.3 不可执行处理

- `unexecutable_count` 单独统计
- 不纳入 win_rate 计算

---

## 2. PortfolioMetrics（组合层指标）

### 2.1 输入

- `fills: list[PaperFill]`
- `initial_cash: Decimal`
- `daily_values: dict[date, Decimal]`（每日总资产）

### 2.2 计算口径

| 指标 | 公式 |
| --- | --- |
| 总收益 | (最终净值 - 初始净值) / 初始净值 |
| 年化收益 | 总收益 / 年数 |
| 夏普率 | (日均收益 - 无风险) / 日收益标准差 × sqrt(252) |
| 最大回撤 | max(peak - trough) / peak |
| 换手率 | Σ(|买入金额| + |卖出金额|) / (初始净值 × 天数) |
| 卡玛率 | 总收益 / 最大回撤 |

### 2.3 输出

```python
@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    initial_cash: Decimal
    final_value: Decimal
    total_return: Decimal
    annualized_return: Decimal
    sharpe_ratio: Decimal | None
    max_drawdown: Decimal
    calmar_ratio: Decimal | None
    turnover: Decimal
    trade_count: int
    days: int
```

---

## 3. BacktestRunManifest 扩展

### 3.1 新增字段

| 字段 | 说明 |
| --- | --- |
| signal_metrics_count | 生成的 SignalMetrics 数量 |
| portfolio_metrics | PortfolioMetrics 快照 |
| evaluation_count | 评价数量 |
| artifact_checksums | 各产物文件 SHA256 |

---

## 4. 产物生成

### 4.1 产物清单

| 产物 | 格式 | 内容 |
| --- | --- | --- |
| `manifest.json` | JSON | 运行元数据、版本、统计 |
| `signals.parquet` | Parquet | SignalEvent 列表 |
| `fills.parquet` | Parquet | PaperFill 列表 |
| `evaluations.parquet` | Parquet | SignalEvaluation 列表 |
| `report.md` | Markdown | 可读报告 |

### 4.2 Parquet 写入

使用 `pyarrow` 或 `pandas` 写入。若不可用，降级为 JSON。

### 4.3 Markdown 报告结构

```markdown
# Backtest Report: {run_id}

## Summary
- run_id, from_time, to_time
- strategy_bindings, sample_count
- unexecutable_count, warnings

## Portfolio Metrics
- 总收益, 夏普率, 最大回撤, 换手率

## Signal Metrics by Bucket
| strategy | symbol | direction | ... | win_rate | avg_net_return |

## Warnings
- 所有 RunWarning 列表
```

---

## 5. 与 Phase 4 的关系

- Phase 4 的 PortfolioLedger 提供 fills 和 daily values
- Phase 3 的 SignalEvent 提供信号数据
- Phase 2 的 BacktestRunResult 提供运行统计

---

## 6. 交付物

| 文件 | 职责 |
| --- | --- |
| `evaluation/metrics.py` | SignalMetrics + PortfolioMetrics |
| `reporting/dimensions.py` | 分桶维度定义 |
| `reporting/tables.py` | 表格生成 |
| `reporting/artifacts.py` | 产物文件写入 |
| `reporting/report_builder.py` | 报告构建（扩展） |
| `tests/backtest/test_portfolio_evaluator.py` | 评价指标测试 |
| `tests/backtest/test_report_builder.py` | 报告生成测试 |
| `docs/reviews/phase-5-review.md` | Review 文档 |
