# Runbook: 信号质量排查

适用于：**信号数量异常、信号分布偏移、信号-收益相关性突变**等场景。

> 适用文档：`docs/architecture/testing-and-evaluation.md` 第 4 节 `Signal Quality`。

## 1. 现象

以下场景之一：

- 同一 `strategy_name` + `strategy_version` 的两次运行 `backtest_signals_generated_total` 偏差 > 30 %；
- `backtest_signals_rejected_total` 突增；
- `backtest_conflicts_total` 出现 > 0；
- Composers 决策变更与策略冻结版本不一致。

## 2. 第一步：校验冻结版本

```bash
python -m quant_signal_system.cli.freeze_status \
  --strategy baseline-rules --strategy-version v1
```

确认 `parameter_hash` 与历史研究一致；若不一致，回滚到上一冻结版本。

## 3. 第二步：查看事件链

```bash
grep '"event_type": "SignalCandidate"' output_dir/event_chain.jsonl \
  | tail -n 5 | jq
```

常见根因：

- **Universe 变更**：上游股票池由 v1→v2；运行应使用 *目标* 时间对应的快照，而非最新版本。
- **数据版本错位**：`data_source_version` 与上次不一致，可能引入新可交易标的或剔除旧标的。
- **特征版本升级**：滚动窗口长度或特征快照策略变化，需重新校准 baseline。

## 4. 第三步：评估信号分布

```bash
python -m quant_signal_system.cli.report_distribution \
  --run-id <run_id> --output report.json
```

关注：

- 每日信号数；
- 行业/股票维度集中度；
- BUY/SELL/HOLD 比例；
- 与上一次"语义等价"运行（相同 parameter_hash + base_time）对比。

## 5. 决策

| 偏差范围 | 处置 |
| --- | --- |
| < 5 % | 正常波动，记录即可 |
| 5 % - 30 % | 标为可疑，对照回放（`make test-replay-golden`）对比 |
| ≥ 30 % | 暂停发行，运行回退流程并提交 review |

## 6. 上下游影响

- `play_reports/` 中的所有报告：以 *信号* 为入口生成的报告必须重新生成。
- 任何基于该信号训练的代理模型：暂停上线，直到信号稳定通过回归。

## 7. 相关文档

- `docs/architecture/strategy-plugin-guide.md`
- `docs/architecture/backtest-observability.md` §4.1
