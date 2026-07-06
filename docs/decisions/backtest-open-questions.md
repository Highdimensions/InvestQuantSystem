# 回测平台开放问题

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 1-7 实施 |
| 与现有 `open-questions.md` 关系 | 互补本文档聚焦回测与研究平台特有决策；已有 `docs/decisions/open-questions.md` 中的 TBD-01 至 TBD-18 继续适用 |
| 最后更新 | 2026-07-03 |

---

## 1. 使用规则

- 信息不足时不得虚构业务指标、性能数据或团队制度
- 所有结论必须标明「已确定 / 建议方案 / 待决策」
- 开放问题在被明确决策前，相关文档和实现应继续标记为「待决策」

---

## 2. 新增开放问题（与现有 open-questions.md 互补）

### 2.1 回测执行相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-01 | **待决策** | 多 symbol FeatureEngine 隔离方案 | 当前单实例已正确隔离，但大规模场景可能有内存压力 | Phase 7 Benchmark 后决定：方案 A（每 binding×symbol 独立实例）vs 方案 B（单实例 + keyed state） |
| BT-TBD-02 | **待决策** | 多 symbol 并行处理 | 当前串行处理；大规模股票池性能可能不足 | Phase 7 Benchmark 后决定；Phase 1-6 保持单线程 |
| BT-TBD-03 | **待决策** | 虚拟时钟与交易日历交互 | 当前 `FrozenClock` 和 `SimpleAshareTradingCalendar` 独立使用；`next_evaluation_time` 依赖日历 | 确认 `VirtualClock.advance` 与 `TradingCalendar.is_session_time` 的交互边界 |
| BT-TBD-04 | **待决策** | Bar 闭合检测时机 | 分钟级 Bar 在 `market_data_time = bar_end_time` 时立即闭合；午间休市如何处理 | 确认 `BarNormalizer` 是否需要在 11:30-13:00 窗口注入虚拟 "CLOSE" 事件 |
| BT-TBD-05 | **待决策** | 事件排序稳定性 | 同一 `market_data_time` 多个 symbol 的 bar 如何稳定排序 | 建议按 symbol 字母序作为二级排序键，ADR 记录决策 |
| BT-TBD-06 | **待决策** | 中断恢复后是否自动继续 | Manifest 存在时，是否支持 `--resume run_id` 自动继续 | 建议 Phase 6 实现；Phase 1-5 强制从头运行 |

### 2.2 股票池相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-07 | **待决策** | Universe 初始来源 | 当前无 Universe 模块；第一版数据从哪来 | 方案 A：手工维护 JSON；方案 B：从现有 AKShare 指数成分自动生成；方案 C：基于 `AsOfDataset` 管理 |
| BT-TBD-08 | **待决策** | Universe 更新触发机制 | 指数成分变化时如何在回测中触发 Universe 切换 | 方案 A：预生成多个 UniverseSnapshot；方案 B：实时查询 `UniverseRepository` |
| BT-TBD-09 | **待决策** | 幸存者偏差控制 | 当前只回测当前仍存在的股票；退市和历史成分如何处理 | 建议 Phase 1 先限制为当前存在的股票，TBD-05 明确后扩展 |

### 2.3 市场规则相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-10 | **待决策** | A 股涨跌幅约束来源 | 当前无涨跌停数据；第一版如何获取 | 方案 A：手工标注涨跌停日；方案 B：从 AKShare 获取涨停股数据；方案 C：基于收盘价计算涨跌停（近似） |
| BT-TBD-11 | **待决策** | ST 和非 ST 区分 | ST 股票涨跌幅为 5%，非 ST 为 10%；ST 状态从哪来 | 同 BT-TBD-10，一起决策 |
| BT-TBD-12 | **待决策** | 停牌数据来源 | 当前无停牌数据；停牌如何判断 | 同 BT-TBD-10，一起决策 |
| BT-TBD-13 | **待决策** | 零股卖出规则 | A 股零股必须一次全部卖出；当前 `default_quantity` 如何处理零股 | 方案 A：舍入到整百；方案 B：拒绝非整百卖出；方案 C：零股时触发自动清仓 |
| BT-TBD-14 | **待决策** | 最高 / 最低佣金 | A 股有最低 5 元佣金限制；是否建模 | 建议 Phase 4 先不建模；Phase 5+ 扩展 |

### 2.4 报告与产物相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-15 | **待决策** | Backtest 结果存储格式 | 当前无存储；产物用 JSON Lines / SQLite / Parquet | 建议：manifest.json（JSON）+ SQLite（信号/评价）+ CSV/JSON Lines（报告）；Parquet 待 Phase 7 Benchmark 评估性能后决定 |
| BT-TBD-16 | **待决策** | 报告格式优先级 | 第一版先支持 Markdown 还是 Jupyter Notebook | 建议 Phase 5 先实现 Markdown；Jupyter Notebook 作为后续选项 |
| BT-TBD-17 | **待决策** | 信号层 / 组合层报告是否分开 | 一次性报告 vs 两份独立报告 | 建议 Phase 5 分离；Signal 层和 Portfolio 层分别生成，避免混淆 |
| BT-TBD-18 | **待决策** | 报告分享格式 | 报告是否需要加密 / 水印 | 当前阶段无需；未来按需评估 |

### 2.5 多策略相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-19 | **待决策** | ComposerDecision 持久化时机 | 当前 `ComposerConflictRecord` 未持久化；Decision 何时写入 | 建议：立即写入 `SignalRepository`（作为 `SignalEvent` 的伴生事实），ADR-BT-003 记录 |
| BT-TBD-20 | **待决策** | 多策略组合是否需要独立持仓 | 当前 `PaperPortfolio` 是全局的；多策略是否共享同一持仓 | 方案 A：全局单持仓（简单）；方案 B：每个 binding_id 独立持仓（组合层归因更清晰）；方案 C：binding 级别持仓 + 组合汇总持仓 |
| BT-TBD-21 | **待决策** | 策略间信号冲突（无 Composer） | 当前只有 Composer 后才有持仓；不同 binding 同时 Buy/Sell 同一标的时如何处理 | 方案 A：全局持仓拒绝后到信号（现有）；方案 B：binding 级别持仓隔离；方案 C：全局持仓 + binding 优先级 |
| BT-TBD-22 | **待决策** | SCORE_WEIGHTED 权重来源 | 当前权重在 `StrategyComposer` 中配置；如何确定 | 建议 Phase 3 先硬编码或从 YAML 读取；自动权重优化作为 Phase 6+ 课题 |

### 2.6 测试相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-23 | **待决策** | 是否引入 `hypothesis` | 当前无属性测试框架；是否引入 | 建议 Phase 1 末尾评估：若 Phase 1 属性测试场景超过 5 个则引入；ADR 记录 |
| BT-TBD-24 | **待决策** | Golden Test 数据集规模 | 当前只有小型 fixture；Golden Case 规模多大合适 | 建议：每个 Golden Case 不超过 30 个 bar；大规模场景用 `pytest.mark.slow` 标记 |

### 2.7 工程相关

| 编号 | 状态 | 问题 | 为什么重要 | 建议决策方式 |
| --- | --- | --- | --- | --- |
| BT-TBD-25 | **待决策** | CLI 框架选型 | 当前无 CLI；用 argparse / click / typer | 建议：Phase 6 先用 `argparse`（无新依赖）；后续按需升级到 `typer` |
| BT-TBD-26 | **待决策** | RunSpec 配置格式 | YAML vs JSON vs TOML | 建议 YAML（与 `StrategyRegistry.yaml_path` 一致）；JSON 作为程序化生成的备选 |
| BT-TBD-27 | **待决策** | 报告自动生成触发方式 | 手动触发 vs 每次回测后自动 | 建议：CLI `run_backtest` 默认自动生成；Python API 可选禁用 |

---

## 3. 与现有开放问题的关系

| 现有 TBD | 与回测平台的关系 |
| --- | --- |
| TBD-01（行情供应商） | 影响回测数据源；`BacktestRunSpec.data_source_profile` 必须冻结供应商配置 |
| TBD-02（交易日历） | 直接影响 `BacktestOrchestrator` 的事件推进；`SimpleAshareTradingCalendar` 实现是基础 |
| TBD-05（股票池范围） | BT-TBD-07/08/09 是 TBD-05 在回测平台的具体落地方式 |
| TBD-08（评价窗口） | 影响 `BacktestRunSpec.evaluation_policies`；必须在 Backtest 开始前冻结 |
| TBD-09（手续费参数） | 直接影响 `FixedBpsCostModel` 的参数；必须版本化 |
| TBD-10（涨跌停模型） | BT-TBD-10/11/12 是 TBD-10 在回测平台的实现方式 |
| TBD-18（Tick 数据） | 影响三重障碍精度；若引入需评估 `BAR_OHLC` vs `TICK` 路径粒度 |

---

## 4. 决策优先级

### 4.1 Phase 1 之前必须决策

| 编号 | 问题 | 决策方式 |
| --- | --- | --- |
| BT-TBD-05 | 事件排序稳定性（symbol 二级排序） | 直接决策，无需数据 |
| BT-TBD-07 | Universe 初始来源 | 建议方案 A（手工 JSON）快速启动 |
| BT-TBD-15 | Backtest 结果存储格式 | 建议 JSON + SQLite |
| BT-TBD-26 | RunSpec 配置格式 | 建议 YAML |

### 4.2 Phase 1 末尾评估

| 编号 | 问题 | 评估方式 |
| --- | --- | --- |
| BT-TBD-23 | 是否引入 `hypothesis` | 统计 Phase 1 属性测试场景数量 |
| BT-TBD-01 | 多 symbol FeatureEngine 隔离 | Phase 7 Benchmark 前先用方案 A |
| BT-TBD-10-12 | A 股市场规则数据来源 | Phase 4 实现前决策 |

---

## 5. 已确定决策

| 编号 | 决策 | 依据 |
| --- | --- | --- |
| DEC-BT-001 | Backtest 无 Manifest 则运行失败 | BLOCK-01 阻断问题 |
| DEC-BT-002 | ComposerDecision 必须持久化 | BLOCK-07 归因链路 |
| DEC-BT-003 | T+1 建模在 Phase 4 实施 | BLOCK-04 阻断问题 |
| DEC-BT-004 | Report 由事实派生，不在 Runner 内拼接 | 架构原则 2.1 |
| DEC-BT-005 | Phase 1 不引入多线程/并行 | 避免过早复杂度 |
| DEC-BT-006 | 属性测试引入需 ADR（`hypothesis`） | 不引入未评估依赖 |
| DEC-BT-007 | Golden Case 变更必须 Review | 防止意外破坏已知行为 |
| DEC-BT-008 | 确定性测试是 Phase 7 基准测试的一部分 | 必须有基线数据才能设定阈值 |
