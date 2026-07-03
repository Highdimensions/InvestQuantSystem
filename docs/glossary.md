# 术语表

相关文档：[开发指导](./architecture/development-guide.md)、[系统上下文](./architecture/system-context.md)、[模块设计](./architecture/module-design.md)、[数据契约](./architecture/data-contracts.md)、[测试与评价](./architecture/testing-and-evaluation.md)、[开放问题](./decisions/open-questions.md)

| 术语 | 状态 | 定义 |
| --- | --- | --- |
| 短线量化交易建议系统 | 已确定 | 用于生成研究性短线 Buy/Sell/Hold 信号并评价有效性的系统 |
| 研究信号 | 已确定 | 仅用于研究和评价的建议，不代表真实交易指令 |
| 模拟成交 | 已确定 | 基于成交模型生成的虚拟成交结果，不代表真实市场成交 |
| 真实交易 | 已确定 | 通过真实券商账户下单和成交；当前系统不支持 |
| `Buy` | 已确定 | 买入或增加风险暴露的研究性方向 |
| `Sell` | 已确定 | A 股场景默认表示减仓、清仓、停止加仓或风险规避，不默认做空 |
| `Hold` | 已确定 | 观望或不改变模拟持仓的研究性方向 |
| `signal_action` | 已确定 | 信号建议动作，如 `BUY`、`REDUCE_LONG`、`CLEAR_LONG`、`RISK_AVOID`、`HOLD` |
| `exposure_effect` | 已确定 | 信号对风险暴露的影响，如增加多头、降低多头、保持空仓 |
| `execution_status` | 已确定 | 信号或评价的可执行状态，如 `EXECUTABLE`、`UNEXECUTABLE`、`UNKNOWN_AT_EVENT_TIME` |
| `MarketTick` | 建议方案 | 标准化逐笔、盘口或行情事件 |
| `MarketBar` | 已确定 | 已闭合的 OHLCV K 线数据 |
| `FeatureSnapshot` | 已确定 | 信号产生时可见特征的快照 |
| `MarketRegime` | 建议方案 | 趋势、震荡、放量、缩量等市场状态标签 |
| `SignalEvent` | 已确定 | 不可变、只追加的信号事实记录 |
| `EvaluationTask` | 建议方案 | 某个信号在某个时间窗口需要执行的评价任务 |
| `SignalEvaluation` | 已确定 | 对某个信号和评价窗口生成的评价事实 |
| `StrategyVersion` | 已确定 | 策略名称、版本、参数、代码和特征版本的组合 |
| `PaperOrder` | 建议方案 | 模拟订单 |
| `PaperFill` | 建议方案 | 模拟成交 |
| `PaperPosition` | 建议方案 | 模拟持仓 |
| `market_data_time` | 已确定 | 行情数据代表的市场时间 |
| `bar_start_time` | 已确定 | Bar 覆盖时间窗口的开始时间 |
| `bar_end_time` | 已确定 | Bar 覆盖时间窗口的结束时间；分钟级 `MarketBar` 的 `market_data_time` 等同于该值 |
| `ingest_time` | 已确定 | 系统接收到数据的时间 |
| `event_time` | 已确定 | 策略产生信号的时间 |
| `executable_time` | 已确定 | 信号最早可被模拟执行的时间 |
| `evaluation_time` | 已确定 | 执行评价的时间 |
| `reference_price` | 已确定 | 信号产生时可观察到的参考价格 |
| `executable_price` | 已确定 | 信号产生后按成交模型得到的可执行价格 |
| `evaluation_price` | 已确定 | 评价窗口对应的现实可获得价格 |
| `data_source_version` | 已确定 | 行情或外部数据源版本 |
| `as_of_version` | 已确定 | 表示当时可见数据版本的标识 |
| `as_of_time` | 已确定 | 观察者在该时间点可见的数据版本时间 |
| `effective_time` | 已确定 | 数据事实生效的时间 |
| `available_at` | 已确定 | 数据对系统现实可获得的时间 |
| `revision_id` | 已确定 | 外部数据修订版本标识 |
| MFE | 已确定 | Maximum Favorable Excursion，最大有利波动 |
| MAE | 已确定 | Maximum Adverse Excursion，最大不利波动 |
| 三重障碍 | 已确定 | 使用止盈、止损和时间障碍标记信号路径的方法 |
| 前视偏差 | 已确定 | 使用信号时点尚不可见的未来信息 |
| 数据泄漏 | 已确定 | 未来标签、未来统计或不可见数据进入特征或训练 |
| 幸存者偏差 | 已确定 | 只使用仍存在或表现较好的标的导致评价偏差 |
| Walk-Forward | 建议方案 | 滚动训练和滚动验证方法，用于降低过拟合风险 |
| 实时影子运行 | 已确定 | 实时运行信号链路但不真实交易，未来再评价信号 |
| 历史回放 | 已确定 | 按历史时间顺序重放行情并驱动同一策略核心 |
| 离线回测 | 已确定 | 在历史数据上模拟信号、成交、成本和持仓结果 |
| 可复现性 | 已确定 | 通过数据、代码、策略、参数和评价版本重建结果的能力 |
| append-only | 已确定 | 只追加写入，不修改历史事实 |
