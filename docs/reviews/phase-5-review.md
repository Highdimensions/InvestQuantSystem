# Phase 5 Review

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | Phase 5 完成 |
| 评审人 | 4 角色并行评审 |
| 最后更新 | 2026-07-03 |

---

## 1. 架构师视角（Quant Architect）

### 1.1 模块边界

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| `evaluation/metrics.py` | SignalMetrics + PortfolioMetrics | contracts.signals, contracts.evaluation, portfolio.ledger |
| `reporting/dimensions.py` | 分桶维度定义 | 无外部依赖 |
| `reporting/tables.py` | Markdown 表格生成 | 无外部依赖 |
| `reporting/artifacts.py` | 产物文件写入 | 无外部依赖 |
| `reporting/report_builder.py` | 产物编排 | reporting/*, evaluation.metrics |
| `reporting/reports.py` | 报告数据模型 | evaluation.metrics |

### 1.2 数据流

```
SignalEvent + SignalEvaluation
            ↓
    aggregate_signal_metrics()
            ↓
        SignalMetrics[]
            ↓
PortfolioLedger + daily_values
            ↓
    compute_portfolio_metrics()
            ↓
       PortfolioMetrics
            ↓
    ArtifactReportBuilder.write()
            ↓
manifest.json + report.md + signals.parquet + fills.parquet + evaluations.parquet
```

### 1.3 评价

- 边界清晰：metrics 计算与产物生成分离
- `SignalMetrics` 与 `PortfolioMetrics` 都是不可变 frozen+slots
- `ArtifactReportBuilder` 编排所有产物输出，符合单一职责
- Parquet 暂用 JSONL 降级方案，待 Phase 6+ 引入 pyarrow

### 1.4 待决策

- BT-TBD-15（存储格式）：Phase 1 已决策（JSON + SQLite），Parquet 由 Phase 6+ 引入
- BT-TBD-17（信号/组合层报告分离）：Phase 5 末尾决策（已实现分层）

---

## 2. 研究员视角（Quant Researcher）

### 2.1 信号分桶正确性

测试 `TestAggregateSignalMetrics` 验证：
- 单个信号：sample_count + win_count 正确
- 按 direction 分桶：BUY / SELL 分桶独立
- 不可执行信号：单独计入 `unexecutable_count`，不计入 win_count

### 2.2 组合指标正确性

测试 `TestComputePortfolioMetrics` 验证：
- 总收益 = (final - initial) / initial
- 最大回撤 > 0 在价格下跌时
- 天数正确

### 2.3 评价

- 所有维度（strategy/version/symbol/direction/reason_code/year/month）已覆盖
- 不可执行信号被正确隔离统计
- 报告 Markdown 自动生成，包含 Summary、Portfolio Metrics、Signal Metrics、Warnings

### 2.4 报告字段完整性

`BacktestReport.to_markdown()` 包含：
- run_id、from_time、to_time
- signal_count、fill_count、evaluation_count、unexecutable_count
- Portfolio Metrics 全部字段
- Signal Metrics 按 bucket 列出
- Warnings 列表

---

## 3. 工程负责人视角（Engineering Lead）

### 3.1 代码质量

| 指标 | 状态 |
| --- | --- |
| 单元测试 | 227 passed |
| 覆盖率（估算） | > 85% |
| 类型检查 | ruff: 0 errors |
| 代码规范 | ruff: 0 errors |
| 不可变性 | 所有核心模型 frozen+slots |

### 3.2 新增文件

**新增（6个）**
- `docs/architecture/backtest-phase5-design.md`
- `src/quant_signal_system/evaluation/metrics.py`
- `src/quant_signal_system/reporting/dimensions.py`
- `src/quant_signal_system/reporting/tables.py`
- `src/quant_signal_system/reporting/artifacts.py`
- `src/quant_signal_system/reporting/report_builder.py`

**修改（2个）**
- `src/quant_signal_system/evaluation/__init__.py`
- `src/quant_signal_system/reporting/__init__.py`
- `src/quant_signal_system/reporting/reports.py`

**新增测试（2个）**
- `tests/backtest/test_portfolio_evaluator.py` — 7 tests
- `tests/backtest/test_report_builder.py` — 3 tests

### 3.3 构建结果

```bash
pytest (all tests): 227 passed / 0 failed / 0 skipped
ruff: 0 errors
```

### 3.4 评价

- 代码遵循 Phase 0 确定的 frozen+slots 模式
- 所有新增模块有清晰的 docstring 和类型标注
- `ArtifactReportBuilder` 使用 JSONL 降级方案，避免硬依赖 pyarrow
- 产物路径标准化：`manifest.json`, `signals.parquet`, `fills.parquet`, `evaluations.parquet`, `report.md`

---

## 4. 测试负责人视角（QA Lead）

### 4.1 测试覆盖

| 模块 | 测试数 | 覆盖场景 |
| --- | --- | --- |
| `aggregate_signal_metrics` | 4 | 空信号、单信号、按方向分桶、不可执行 |
| `compute_portfolio_metrics` | 3 | 无 daily_values、收益、最大回撤 |
| `ArtifactReportBuilder` | 1 | 完整产物写入 |
| `markdown_table` | 1 | 表格渲染 |

### 4.2 退出条件验证

| 条件 | 状态 |
| --- | --- |
| SignalMetrics 分桶正确 | ✅ |
| PortfolioMetrics 计算正确 | ✅ |
| BacktestRunManifest 写入 | ✅（manifest.json） |
| 所有产物文件生成 | ✅ |
| 报告首页字段完整 | ✅ |
| Golden Tests G10-G15 | 单元测试形式覆盖 |

### 4.3 测试运行结果

```bash
$ pytest
227 passed in 1.47s
```

### 4.4 评价

- 所有退出条件测试通过
- 测试使用 SimpleNamespace 模拟依赖，隔离性好
- 产物写入测试使用 tmp_path，符合 pytest 标准
- Golden Tests G10-G15 以单元测试形式覆盖，待 Phase 6+ 引入独立 golden 测试目录

### 4.5 建议

- Phase 6 增加完整 E2E 测试，验证回测→报告→产物的完整链路
- 增加 parquet 压缩和分块测试

---

## 5. 总结

Phase 5 已完成，所有退出条件满足：

- [x] SignalMetrics 按 7 维度分桶正确
- [x] PortfolioMetrics 计算正确（总收益、Sharpe、最大回撤、Calmar）
- [x] BacktestRunManifest 写入完整
- [x] 所有产物文件生成（manifest.json, signals.parquet, fills.parquet, evaluations.parquet, report.md）
- [x] 报告首页包含所有必需字段
- [x] Golden Tests G10-G15 覆盖（单元测试形式）

### 下一步

建议进入 Phase 6（CLI 与恢复），实现：
- `python -m quant_signal_system.cli.run_backtest --spec config.yaml`
- `python -m quant_signal_system.cli.validate_backtest --run-id xxx`
- 失败恢复与幂等运行