# 测试、评价与可观测性设计

相关文档：[开发指导](./development-guide.md)、[系统上下文](./system-context.md)、[模块设计](./module-design.md)、[数据契约](./data-contracts.md)、[术语表](../glossary.md)、[开放问题](../decisions/open-questions.md)

## 1. 范围

已确定：本文件覆盖系统正确性测试、量化研究正确性约束、信号有效性评价、历史回放与回测验证、实时影子对账、故障恢复和可观测性。

已确定：信号质量评价不等同于收益承诺。所有结果必须标明数据版本、策略版本、评价口径、成本假设和样本范围。

## 2. 量化研究正确性约束

| 风险 | 状态 | 风险是什么 | 系统中如何发生 | 架构预防 | 测试发现 |
| --- | --- | --- | --- | --- | --- |
| 前视偏差 | 已确定 | 使用信号时刻不可见的未来信息 | 用当前未闭合 Bar 的最终 high/low/close 生成信号 | 只允许已闭合 `MarketBar` 进入策略 | 构造边界 Bar，断言特征窗口不含未来 |
| 数据泄漏 | 已确定 | 标签或未来统计进入特征 | 全量标准化、用未来成交量补缺失值 | `FeatureSnapshot` 记录输入范围和版本 | 训练/回放 fixture 检查时间边界 |
| 未闭合 K 线 | 已确定 | 使用仍在变化的 Bar | 实时聚合时提前推送分钟 Bar | Bar Aggregator 明确闭合事件 | Tick 到 Bar 测试覆盖分钟边界 |
| 幸存者偏差 | 已确定 | 只回测当前仍存在标的 | 扩展多股票时忽略退市、停牌、指数历史成分 | 股票池版本化 | 多股票前将数据集要求列为门槛 |
| 参数过拟合 | 已确定 | 在同一数据上反复调参只展示最佳结果 | 批量参数搜索后选择性汇报 | 记录参数搜索空间和 run metadata | Walk-Forward 和样本外验证 |
| 选择性展示 | 已确定 | 只展示好看的时间段或分桶 | 报告隐藏失败样本 | 报告强制展示样本量、失败和全部版本 | 报告契约测试检查必备指标 |
| 成本低估 | 已确定 | 忽略手续费、税、价差、滑点和延迟 | 使用 reference price 直接算收益 | `executable_price` 和成本模型必填 | Golden case 验证净收益 |
| 时间戳错位 | 已确定 | 混用市场时间、接收时间和评价时间 | 用 `ingest_time` 当市场时间 | 明确五类时间字段 | 契约测试和排序测试 |
| 数据修订 | 已确定 | 未来修订数据覆盖当时可见数据 | 供应商回补后重算历史信号 | 数据版本和 replay run 隔离 | 修订数据 fixture 对比 |
| 回测与实时分叉 | 已确定 | 两套策略逻辑逐渐不同 | `backtest_signal.py` 与 `live_signal.py` 各自实现 | 共享 `FeatureEngine` 和 `StrategyRuntime` | 实时/回放一致性测试 |

## 3. 信号有效性评价

### 3.1 评价层级

| 层级 | 状态 | 对象 | 输出 |
| --- | --- | --- | --- |
| 信号级评价 | 已确定 | 单个 `SignalEvent` | 固定窗口收益、方向标签收益、净收益、MFE、MAE、三重障碍 |
| 策略级评价 | 已确定 | 同一 `strategy_name` / `strategy_version` | 分桶统计、命中率、期望收益、Profit Factor、最大连续失败 |
| 组合级评价 | 建议方案 | `PaperPortfolio` | 模拟持仓、订单、成交、资金曲线、回撤和成本 |

### 3.2 指标定义

| 指标 | 状态 | 定义 |
| --- | --- | --- |
| 固定时间窗口收益 | 已确定 | `evaluation_price / executable_price - 1` |
| 方向标签收益 | 已确定 | `direction * raw_return`，只用于判断信号方向是否正确 |
| 模拟持仓收益 | 已确定 | 基于 `PaperFill` 和 `PaperPosition` 计算；A 股默认不允许 `Sell` 产生空头收益 |
| 净收益 | 已确定 | 方向标签收益扣除手续费、税、价差、滑点和延迟成本 |
| MFE | 已确定 | 信号后到评价窗口内沿正确方向的最大有利波动 |
| MAE | 已确定 | 信号后到评价窗口内沿错误方向的最大不利波动 |
| 三重障碍标签 | 已确定 | 止盈、止损、时间障碍中先触发者 |
| 达到止盈/止损时间 | 已确定 | 从 `executable_time` 到首次触发障碍的时间 |
| 信号覆盖率 | 建议方案 | 信号数量占可产生信号机会数比例 |
| 命中率 | 建议方案 | 方向标签收益或净收益大于零的比例 |
| 期望收益 | 建议方案 | 单信号平均净收益或按收益分布计算的期望值 |
| Profit Factor | 建议方案 | 总正收益 / 总负收益绝对值 |
| 最大连续失败 | 建议方案 | 连续净收益小于等于零的最大次数 |
| 置信度校准 | 建议方案 | 置信度分桶与实际表现的匹配程度 |

已确定：不可执行样本必须纳入报告分母，展示 `execution_status`、`unexecutable_reason`、数量和占比。不得因为涨跌停、停牌、成交量不足或可执行价格不可得而静默剔除样本。

建议方案：MFE、MAE 和三重障碍使用 `[executable_time, evaluation_time]` 路径。`path_granularity = BAR_OHLC` 且同一 Bar 同时触发止盈和止损时，默认结果为 `AMBIGUOUS`，或按文档化的保守规则处理；需要严格先后顺序时必须使用 Tick 路径。

### 3.3 分桶统计

建议方案：至少按以下维度分桶展示，且每个分桶必须展示样本量。

- `strategy_version`
- `feature_version`
- 市场状态 `MarketRegime`
- 时间段，如开盘后、午前、午后、尾盘
- 波动率分桶
- 成交量分桶
- 信号强度分桶
- 置信度分桶
- 标的、行业或板块，具体数据来源待决策

## 4. 分层测试策略

| 测试层 | 对象 | 输入 | 断言 | 通过条件 |
| --- | --- | --- | --- | --- |
| 单元测试 | 指标、收益、MFE、MAE、三重障碍 | 手工构造小数组 | 边界和方向计算正确 | 全部确定性用例通过 |
| 属性测试 | 收益和窗口函数 | 随机价格序列 | 不使用未来窗口，不产生非法状态 | 不变量始终成立 |
| 数据契约测试 | `MarketBar`、`SignalEvent`、`SignalEvaluation` | 合法与非法样本 | 必填字段、时间顺序、版本字段正确 | 非法样本被拒绝 |
| 集成测试 | Normalizer 到 Repository | 小型行情 fixture | 信号持久化且评价任务生成 | 端到端链路可重放 |
| 历史回放测试 | Historical Replay Engine | 固定历史日 fixture | 同输入同版本同输出 | Golden output 稳定 |
| 回测正确性测试 | Backtest Engine、PaperPortfolio | 成本、滑点、涨跌停 fixture | 成交和净收益符合假设 | Golden case 通过 |
| 实时/回放一致性测试 | Live shadow vs Replay | 同期标准化 Bar | 信号数量、特征、方向、分数一致或差异有解释 | 规则策略未解释差异为零 |
| 故障恢复测试 | Repository、Scheduler、Evaluator | 中断、重复、部分写入 | 重启后不丢不重 | 非性能类硬门槛通过 |
| 长时间稳定性测试 | 实时影子链路 | 连续运行数据 | 无无界积压、延迟可观测 | 阈值待基准测试确定，未确定前不得作为阶段晋级依据 |
| 性能测试 | 数据到信号和评价延迟 | 基准数据流 | 分位延迟、吞吐 | 目标待基准测试确定 |
| 模型有效性评价 | 策略和模型 | 样本外或 Walk-Forward 数据 | 报告样本量、分桶、成本和失败 | 不选择性展示 |

## 5. Golden Case

建议方案：第一版至少维护以下可复现用例。

- 一个盈利 `Buy` 信号。
- 一个亏损 `Buy` 信号。
- 一个 `Sell` 作为风险规避信号。
- 一个 `Hold` 信号。
- 一个因涨跌停、停牌或成交量不足无法模拟成交的信号。
- 一个持仓期间重复信号。
- 一个先触发止盈再回落的三重障碍用例。
- 一个先出现 MAE 后出现 MFE 的路径用例。
- 一个 OHLC 同 Bar 同时触发止盈和止损的 `AMBIGUOUS` 用例。
- 一个 `Sell` 只能减仓或清仓、不能产生负持仓的模拟持仓用例。

## 6. 实时影子运行对账

建议方案：实时影子运行每天或每个研究批次生成对账报告。

| 指标 | 含义 |
| --- | --- |
| Signal match rate | 实时与回放信号匹配率 |
| Missing signal count | 实时有、回放无或回放有、实时无的数量 |
| Timestamp delta | `market_data_time`、`event_time` 和 `ingest_time` 差异 |
| Feature delta | 同一 Bar 下特征快照差异 |
| Score delta | 信号强度差异 |
| Evaluation completeness | 应评价窗口完成比例 |
| Duplicate rate | 重复行情或重复信号比例 |
| Missing-data rate | 缺失 Bar 或缺失字段比例 |

已确定：对确定性规则策略，未解释的信号差异应视为系统缺陷。

## 7. 故障恢复设计

| 故障点 | 检测 | 恢复 | 幂等键 |
| --- | --- | --- | --- |
| 行情接入中断 | 数据延迟和缺失 Bar 指标 | 重连、补拉、标记缺口 | `(source, symbol, market_data_time, sequence)` |
| 标准化失败 | quarantine 计数 | 修复映射后重放 | 原始事件 ID |
| 信号写入失败 | Repository 错误 | 重试，必要时重放 Bar | `signal_id` |
| 评价任务中断 | due task 积压 | 扫描 `SignalEvent` 与 `SignalEvaluation` 差集 | `(signal_id, horizon_seconds)` |
| 评价写入部分失败 | 写入错误和缺失评价 | upsert 或重新执行 | `(signal_id, horizon_seconds, evaluator_version)` |
| 报告生成失败 | 报告任务错误 | 重算派生数据 | run id |

建议方案：评价任务恢复必须覆盖以下故障注入用例。

- `claim` 成功后 Worker 崩溃，租约过期后任务可重新领取。
- `SignalEvaluation` 写入成功但 `EvaluationTask` 完成标记失败，重试后不产生重复评价。
- 两个 Worker 同时抢同一任务，只有一个持有有效租约。
- 行情暂不可用时任务进入 `POSTPONED`，到 `next_retry_at` 后重新检查。

## 8. 可观测性

### 8.1 结构化日志字段

建议方案：

- `trace_id`
- `symbol`
- `market_data_time`
- `ingest_time`
- `event_time`
- `strategy_name`
- `strategy_version`
- `feature_version`
- `signal_id`
- `evaluation_horizon_seconds`
- `run_id`
- `error_code`

### 8.2 Metrics

建议方案：

| 指标 | 类型 | 建议标签 | 用途 |
| --- | --- | --- | --- |
| `market_data_latency_ms` | 分位延迟 | `source`, `symbol`, `timeframe` | 行情延迟和告警 |
| `normalization_error_count` | 计数 | `source`, `error_code` | 标准化质量 |
| `missing_bar_count` | 计数 | `symbol`, `timeframe`, `data_source_version` | 缺失数据诊断 |
| `out_of_order_event_count` | 计数 | `source`, `symbol` | 乱序诊断 |
| `duplicate_event_count` | 计数 | `source`, `symbol` | 去重效果 |
| `feature_latency_ms` | 分位延迟 | `strategy_version`, `feature_version` | 性能基准 |
| `signal_generation_latency_ms` | 分位延迟 | `strategy_version` | 信号链路延迟 |
| `signal_persist_failure_count` | 计数 | `repository`, `error_code` | P1 告警 |
| `due_evaluation_task_count` | 计数 | `horizon`, `status` | 评价积压 |
| `oldest_due_evaluation_age_seconds` | gauge | `horizon` | 恢复和积压告警 |
| `evaluation_retry_count` | 计数 | `horizon`, `error_code` | 重试诊断 |
| `quarantine_queue_size` | gauge | `source`, `reason` | 数据质量告警 |
| `worker_heartbeat_age_seconds` | gauge | `worker_id`, `worker_type` | Worker 存活 |
| `clock_skew_ms` | gauge | `host`, `source` | 时间戳错位告警 |
| `replay_mismatch_count` | 计数 | `run_id`, `strategy_version` | 实时/回放对账 |
| `dashboard_query_latency_ms` | 分位延迟 | `endpoint` | 展示性能 |

待决策：具体阈值需通过基准测试和影子运行数据确定。阈值未确定前，不得把性能类指标作为“已通过”的阶段门槛。

### 8.3 告警分级

| 等级 | 条件建议 | 响应 |
| --- | --- | --- |
| P1 | `signal_persist_failure_count > 0` 持续超过待定窗口；`oldest_due_evaluation_age_seconds` 超过基准阈值；`clock_skew_ms` 超过基准阈值 | 立即处理，暂停相关结果解释 |
| P2 | 行情延迟升高、缺失 Bar、quarantine 增长、实时/回放差异增加 | 当日排查，标记受影响 run |
| P3 | Dashboard 慢查询、单个策略异常、报告生成失败 | 排期修复，不阻塞事实写入 |

待决策：每条告警必须在实现前补齐 `metric`、聚合窗口、持续时间、路由对象、runbook 链接和是否暂停结果解释。具体阈值待基准测试和运行数据确定。

### 8.4 最小运行手册

建议方案：进入实时影子运行前至少准备以下 runbook。

- 数据断流或延迟升高：检查行情源、Adapter、quarantine、缺失 Bar 和补拉状态。
- 评价任务积压：检查 Worker heartbeat、租约过期、重试错误和最老到期任务年龄。
- 写入失败：检查 Repository 错误、幂等键冲突和存储容量。
- 实时/回放差异增加：固定数据版本、策略版本、特征版本和参数哈希后重放对账。
- Dashboard 查询慢：确认只影响展示层，不阻塞信号持久化和评价写入。

## 9. 发布与验收门槛

已确定：

- 单元、契约、回放和评价测试通过。
- 契约非法样本拒绝率为 100%。
- Golden replay 输出稳定，变更必须有明确版本说明。
- 确定性规则策略的 Golden replay 未解释差异为 0。
- 同一 `(signal_id, horizon, evaluation_policy_version, data_source_version)` 重复执行只产生一条评价结果。
- 故障恢复后无丢失评价、无重复评价。
- 回测正确性测试覆盖成本、滑点、延迟、涨跌停、停牌和重复信号。
- 实时影子运行与历史回放对账报告无未解释差异。
- 可观测性至少覆盖数据延迟、信号耗时、评价积压、缺失 Bar 和重复事件。
- 最小 runbook 已创建并通过演练。
- 开放问题不会被写成已确定事实。
