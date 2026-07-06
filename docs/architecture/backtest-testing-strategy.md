# 回测平台测试策略

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 1-7 实施 |
| 相关文档 | [当前状态审计](../reviews/backtest-current-state-audit.md)、[目标架构](./backtest-target-architecture.md)、[核心领域模型](./backtest-domain-model.md)、[数据契约](./backtest-data-contracts.md) |
| 最后更新 | 2026-07-03 |

---

## 1. 测试策略总览

### 1.1 7 类测试

| 编号 | 测试类型 | 目标 | 工具 | 新增/已有 |
| --- | --- | --- | --- | --- |
| T1 | 单元测试 | 每个模型和模块的正确性 | pytest | 新增 |
| T2 | 属性测试 | 关键不变量对任意输入成立 | `hypothesis` | 待 ADR |
| T3 | Golden Tests | 固定输入的确定性输出 | pytest + fixture | 新增 |
| T4 | 历史回放一致性测试 | 相同输入产生一致输出 | pytest | 新增 |
| T5 | 实时影子对账测试 | 实时与回放一致 | pytest | 新增 |
| T6 | 故障测试 | 中断和恢复的正确性 | pytest | 新增 |
| T7 | Fuzz 测试 | 随机输入发现崩溃和状态污染 | `hypothesis` | 待 ADR |

### 1.2 测试目录规划

```
tests/
  unit/                        # 已存在
  contract/                    # 已存在
  integration/                 # 已存在
  strategies/                  # 已存在
  # ── 新增 ──
  backtest/
    test_run_spec.py           # RunSpec 校验
    test_universe.py           # UniverseSnapshot
    test_strategy_binding.py  # StrategyBinding
    test_orchestrator.py       # Orchestrator
    test_state_partition.py    # 状态隔离
    test_composer_decision.py  # ComposerDecision 持久化
    test_market_rules.py      # 市场规则引擎
    test_portfolio_ledger.py  # 账本守恒
    test_order_intent.py       # OrderIntent
  golden/
    test_single_symbol_single_strategy.py
    test_single_symbol_multi_strategy.py
    test_multi_symbol_single_strategy.py
    test_multi_symbol_multi_strategy.py
    test_t_plus_1.py
    test_limit_up_down.py
    test_suspended.py
    test_lunch_break.py
    test_duplicate_bar.py
    test_missing_bar.py
    test_out_of_order_bar.py
    test_data_revision.py
    test_universe_change.py
    test_same_strategy_different_params.py
  consistency/
    test_replay_consistency.py
    test_live_vs_replay.py
  reconciliation/
    test_shadow_reconciliation.py
  fault/
    test_mid_run_failure.py
    test_partial_persistence.py
    test_duplicate_task_execution.py
    test_data_interruption.py
  property/
    test_determinism.py
    test_money_conservation.py
    test_t_plus_1_property.py
    test_cost_monotonicity.py
  fuzz/
    test_runspec_fuzz.py
    test_bar_sequence_fuzz.py
    test_universe_fuzz.py
```

---

## 2. 单元测试（T1）

### 2.1 覆盖范围

| 模块 | 测试点 | 验证内容 |
| --- | --- | --- |
| `backtest/run_spec.py` | `BacktestRunSpec` 校验 | `from_time < to_time`；`strategy_bindings` 非空；Universe 可见性 |
| `backtest/manifest.py` | `BacktestRunManifest` 序列化 | 完整字段写入/读取一致 |
| `backtest/orchestrator.py` | 执行流程 | 信号数、评价任务数符合预期 |
| `universe/contracts.py` | `UniverseSnapshot` as-of | `available_at <= decision_time` 拒绝 |
| `universe/repository.py` | Universe 版本查询 | 正确返回 latest effective |
| `execution/market_rules.py` | T+1 规则 | 当日买入不可卖 |
| `execution/market_rules.py` | 涨跌停规则 | 涨停不可买、跌停不可卖 |
| `execution/market_rules.py` | 停牌规则 | 停牌不可交易 |
| `execution/market_rules.py` | 整数手规则 | 零股处理 |
| `execution/order_model.py` | 资金充足性 | 资金不足时拒绝 |
| `portfolio/ledger.py` | 现金守恒 | 买入后现金减少，买入后持仓增加 |
| `portfolio/ledger.py` | 借贷平衡 | 资产 = 现金 + 持仓市值 |
| `portfolio/settlement.py` | T+1 持仓可用性 | 当日新增持仓标记为不可卖 |
| `reporting/dimensions.py` | 分桶维度 | 每个维度正确分组 |
| `reporting/tables.py` | Markdown 表格格式 | 列对齐、样本量展示 |
| `strategies/composer.py` | 冲突记录持久化 | `ComposerDecision` 写入 |
| `strategies/composer.py` | 冲突归因 | 被拒候选的 `rejection_reason` 正确 |
| `evaluation/evaluator.py` | 参数 Hash 稳定性 | 相同参数产生相同 Hash |
| `evaluation/evaluator.py` | 参数 Hash 变更检测 | 不同参数产生不同 Hash |

### 2.2 现有单元测试补充

| 文件 | 补充场景 |
| --- | --- |
| `tests/unit/test_sqlite_signal_repository.py` | 多股票信号；并发写入冲突 |
| `tests/unit/test_time_sqlite_validation.py` | 非交易日数据写入；跨时区边界 |
| `tests/unit/test_market_data_repository_reconciliation.py` | 多数据源版本切换 |

---

## 3. 属性测试（T2）

### 3.1 依赖评估

**选项 A：引入 `hypothesis`**

| 维度 | 评估 |
| --- | --- |
| 功能 | 工业级属性测试框架，支持端点覆盖、统计测试 |
| 仓库适配 | Python 原生，与 pytest 集成良好 |
| 许可证 | Mozilla Public License 2.0（MPL 2.0） |
| 引入风险 | 低（MPL 许可宽松，不传染） |
| 决策 | **建议方案**：Phase 1 末尾引入，先在新目录 `tests/property/` 中试用 |

**选项 B：纯 pytest-parametrize**

- 优点：无新增依赖
- 缺点：只覆盖固定组合，无法生成随机边界值
- 决策：不推荐，但 Phase 1 期间可用作过渡

### 3.2 关键不变量清单

| 编号 | 不变量 | 测试方法 | 预期 |
| --- | --- | --- | --- |
| P1 | 相同输入重复运行结果一致 | 生成固定 MarketBar 序列，重复运行，比较 `signal_ids` | 完全一致 |
| P2 | 手续费增加时净收益不上升 | 参数化 cost_rate，比较净收益 | 成本越高，净收益越低或相等 |
| P3 | 滑点增加时净收益不上升 | 参数化 slippage，比较净收益 | 滑点越高，净收益越低或相等 |
| P4 | 无持仓时不得产生卖出成交 | 无 `SignalEvent(SIDE=BUY)` 的情况下运行 | `PaperFill` 中无 `SELL` |
| P5 | T+1 下当日新增仓位不得成为可卖仓位 | 买入后立即尝试卖出 | 第二次 `apply_signal(SELL)` 返回空 |
| P6 | 现金和资产守恒 | 买入前后检查 `cash + position_value` | 守恒（忽略成本时） |
| P7 | 交易后账本借贷平衡 | 多笔交易后检查 `cash + long_position_value - short_position_value` | 等于初始现金 |
| P8 | 不同 Symbol 的状态互不影响 | 同时喂入 symbol A 和 B，检查各自特征状态 | 互不污染 |
| P9 | 无界内存增长 | 连续 N 个 bar 后检查 `_bars_by_symbol` 长度 | 长度有界（不超过 lookback window） |
| P10 | 时间不退 | `FrozenClock.advance()` 只接受正向 delta | 负向 delta 抛出 |

---

## 4. Golden Tests（T3）

### 4.1 Golden Case 清单

| 编号 | Case | 输入 | 预期输出 |
| --- | --- | --- | --- |
| G1 | 单股票单策略 | 300346 日线 30 日，VOLUME_BREAKOUT 策略 | 固定数量的 BUY 信号 |
| G2 | 单股票多策略冲突 | 同一股票，同上，但 BUY 策略 vs SELL 策略 | 按 policy 选胜者或 abstained |
| G3 | 多股票单策略 | 300346 + 600519 同策略 | 各自独立信号，互不影响 |
| G4 | 多股票多策略 | 300346 + 600519，多个策略绑定不同 universe | 各自独立 binding 输出 |
| G5 | T+1 阻断 | 买入后立即收到 SELL | SELL 成交被阻断（无可卖持仓） |
| G6 | 涨停买入失败 | 涨停日收到 BUY 信号 | OrderIntent REJECTED（limit_up） |
| G7 | 跌停卖出失败 | 跌停日收到 SELL 信号 | OrderIntent REJECTED（limit_down） |
| G8 | 停牌 | 停牌期间收到信号 | OrderIntent REJECTED（suspended） |
| G9 | 午间休市 | 11:30 收到信号 | executable_time 推进到 13:00 |
| G10 | 重复 Bar | 同一 market_data_time 的两个 Bar | 保留第一个，第二个进入 quarantine |
| G11 | 缺失 Bar | 预期 1 分钟间隔，实际缺失 3 分钟 | 记录 WARNING，跳过 |
| G12 | 乱序 Bar | Bar 按非时间顺序输入 | 内部重排后处理，不改变结果 |
| G13 | 数据修订 | Bar v1 后同一时间戳 Bar v2 | 隔离第二个，进入 quarantine |
| G14 | Universe 成分变化 | 2025-06-30 标的被调出 | 变化前信号正常，变化后停止 |
| G15 | 同策略不同参数 | 同一策略，参数 A vs 参数 B | 各自独立 binding，信号不同 |

### 4.2 Golden Fixture 格式

每个 Golden Case 包含：

```
tests/golden/
  <case_name>/
    description.md          # 人工可读的用例描述和期望结果
    input/
      market_bars.json      # 输入 MarketBar 序列
      strategy_bindings.yaml # 策略绑定配置
      universe.json         # 股票池快照（若涉及）
    expected/
      signal_events.json    # 期望的 SignalEvent 序列
      order_intents.json    # 期望的 OrderIntent 序列
      fills.json           # 期望的 PaperFill 序列
      manifest.json        # 期望的 Manifest 统计
    _notes.md              # 人工计算说明和假设
```

### 4.3 Golden 变更规则

- Golden 文件变更必须显式 Review，不得自动覆盖
- 变更理由必须写入 `_notes.md`
- CI 必须运行 `pytest tests/golden/` 并对比哈希

---

## 5. 历史回放一致性测试（T4）

### 5.1 测试框架

```python
def test_replay_consistency():
    bars = load_golden_bars("tests/golden/single_symbol_single_strategy/input/market_bars.json")

    # 通过 Backtest Runtime
    result_replay = run_backtest(bars, spec=spec_replay)

    # 通过 Historical Replay Runtime
    result_historical = run_historical_replay(bars, spec=spec_replay)

    # 比较
    assert result_replay.signal_ids == result_historical.signal_ids
    assert result_replay.signal_events == result_historical.signal_events
```

### 5.2 允许差异字段白名单

以下字段在比较时排除：

- `event_time`（系统时间戳有微小差异）
- `ingest_time`（接收时间不同）
- `generated_at`（FeatureSnapshot 时间戳）
- `created_at`（Manifest 时间戳）
- `completed_at`（Manifest 时间戳）

### 5.3 关键断言

| 编号 | 断言 |
| --- | --- |
| C1 | `signal_id` 序列完全一致 |
| C2 | `SignalEvent.direction` 完全一致 |
| C3 | `SignalEvent.score` 精度一致（`Decimal` 比较） |
| C4 | `FeatureSnapshot.features` 内容一致 |
| C5 | `ComposerDecision.decision` 一致 |
| C6 | `ComposerDecision.candidates` 数量一致 |

---

## 6. 实时影子对账测试（T5）

### 6.2 测试框架

```python
def test_live_vs_replay():
    # 固定时间段
    from_time = datetime(2025, 6, 1)
    to_time = datetime(2025, 6, 5)

    # 实时运行（模拟）
    shadow_signals = run_shadow(symbols=["300346"], from_time=from_time, to_time=to_time)

    # 同时间段历史回放
    replay_signals = run_backtest(symbols=["300346"], from_time=from_time, to_time=to_time)

    # 比较
    report = ShadowRunComparator.compare(
        replay_signals=replay_signals,
        shadow_signals=shadow_signals,
    )

    assert report.unexplained_differences == 0
```

### 6.3 对账报告字段

| 字段 | 说明 |
| --- | --- |
| `missing_in_shadow` | 回放有、影子无的 signal_id |
| `extra_in_shadow` | 影子有、回放无的 signal_id |
| `direction_mismatches` | signal_id 相同但方向不同的 |
| `timestamp_delta_max` | 最大时间戳差异（毫秒） |
| `feature_delta_max` | 最大特征值差异 |

---

## 7. 故障测试（T6）

### 7.1 故障矩阵

| 故障点 | 注入方式 | 预期状态 | 幂等键 | 重启后断言 |
| --- | --- | --- | --- | --- |
| 中途进程失败 | `SIGKILL` | `run_status=partial` | `run_id` | Manifest 可读，部分数据已落盘 |
| Manifest 写入失败 | mock 抛出异常 | `run_status=failed` | 无 | Manifest 不存在 |
| 部分事实数据已落盘 | 在写入中间中断 | `run_status=partial` | 多次 `run_id` | 同一 `run_id` 可重新运行，数据幂等 |
| 评价任务重复执行 | 两 Worker 同时 claim | 只有一个成功 | `EvaluationTaskKey` | 重复执行不产生重复评价 |
| 数据源中断 | 模拟断流 | `warnings` 含 `DATA_INTERRUPTION` | 无 | 断流后恢复，数据无损坏 |
| 非法版本混合 | 注入不同 `data_source_version` 的 bar | 拒绝或隔离 | 无 | 数据进入 quarantine |
| 重复 run_id | 相同配置运行两次 | 幂等跳过或覆盖 | `run_id` | Manifest 一致 |
| 恢复后幂等 | 中断后重新运行 | 无重复信号 | `signal_id` | 信号数量不变 |

### 7.2 恢复测试

```
正常运行
  ↓
SIGKILL（进程崩溃）
  ↓
重启，重新执行相同 run_id
  ↓
验证：
  - signal_events 无重复
  - evaluation_tasks 无重复
  - Manifest run_status 一致
  - 前半段结果与中断前完全一致
```

---

## 8. Fuzz 测试（T7）

### 8.1 目标对象

| 对象 | Fuzz 策略 | 发现目标 |
| --- | --- | --- |
| `BacktestRunSpec` | 随机组合 strategy_bindings, time_range | 配置校验崩溃 |
| `MarketBar` 序列 | 随机时间戳、重复、乱序 | 状态污染、非确定性 |
| 事件排序 | 随机事件类型乱序 | 时间倒退、状态不一致 |
| `UniverseSnapshot` | 随机 symbols, effective_time | as-of 边界错误 |
| Composer 输入 | 随机 candidate 集合 | 冲突解决逻辑崩溃 |
| 订单序列 | 随机 BUY/SELL/数量 | 资金不守恒、负持仓 |

### 8.2 发现标准

每次 Fuzz 运行结束后验证：

- 无 Python 异常（`Exception`）
- 无断言失败（`AssertionError`）
- `cash >= 0`
- `position_qty >= 0`（A 股无空仓）
- `time` 从不倒退

---

## 9. 测试命令规划

```powershell
# 单元测试
pytest tests/backtest/ tests/unit/ tests/strategies/

# Golden Tests
pytest tests/golden/

# 属性测试（引入 hypothesis 后）
pytest tests/property/

# 一致性测试
pytest tests/consistency/

# 故障测试
pytest tests/fault/

# Fuzz 测试（引入 hypothesis 后）
pytest tests/fuzz/

# 全部测试
pytest
```

**Phase 1 末尾评估**：是否引入 `hypothesis`。若引入，需要记录 ADR。

---

## 10. 缺失场景汇总（Phase 0 审计结果）

| 场景 | 编号 | 说明 |
| --- | --- | --- |
| 多股票回测 | T1-01 | 所有测试仅用 `000001` |
| 多策略 + 多股票 | T1-02 | 仅单策略或单股票 |
| BacktestRunner 单元测试 | T1-03 | 无直接测试 |
| 报告自动生成测试 | T1-04 | `EvaluationReportBuilder` 无测试 |
| 属性测试 | T2-01 | 仅参数哈希稳定性 |
| Golden Tests（价格路径） | T3-01 | 仅数据对账 |
| 故障恢复测试 | T6-01 | `evaluation-recovery` 存在但不完整 |
| T+1 建模测试 | T1-05 | 无 |
| 涨跌停测试 | T1-06 | 无 |
| 并发安全测试 | T1-07 | 无 |
| 确定性与可复现测试 | T4-01 | 无 |
| Fuzz 测试 | T7-01 | 无 |
