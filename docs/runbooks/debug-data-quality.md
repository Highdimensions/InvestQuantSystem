# Runbook: 数据质量排查

适用于：**行情数据缺失、乱序、重复、修订未生效**等场景。

> 适用文档：`docs/architecture/backtest-testing-strategy.md` 第 6 节 `Data Quality Golden Cases`。

## 1. 现象

`BacktestRunManifest` 的 `data_quality` 字段出现以下计数：

- `missing_bar_count > 0`
- `duplicate_bar_count > 0`
- `out_of_order_bar_count > 0`
- `quarantine_record_count > 0`

或 `warnings` 列表中存在以下 `warning_code`：

- `MISSING_BAR`
- `OUT_OF_ORDER_BAR`
- `DUPLICATE_BAR`
- `BAR_REVISION`

## 2. 一级响应

1. **不要根据此次结果做出交易决策或策略优化调整**。所有命中上述告警的运行均视为研究性数据，不应当自动触发下游动作。
2. 拷贝 `manifest.json` 到问题工单，记录以下字段：
   - `run_id`
   - `data_source_version`
   - `as_of_version`
   - 各计数器的具体值
3. 比较 `manifest.resolved_config_hash` 与上一次可用的运行，确认是否为同一份 spec。

## 3. 进一步排查

### 3.1 缺失 Bar

```bash
grep '"warning_code": "MISSING_BAR"' output_dir/warnings.jsonl \
  | jq -c '{symbol: .affected_symbols[0], from: .affected_time_range[0], to: .affected_time_range[1]}'
```

检查点：

- 数据源在该时段是否公告中断？
- `data_source_version` 是否与已确认最新版本一致？
- A 股是否处于午休/集合竞价时段（`MarketBar.trading_status`）？

### 3.2 乱序 Bar

```bash
grep '"warning_code": "OUT_OF_ORDER_BAR"' output_dir/warnings.jsonl \
  | jq -c '{sequence: .event_sequence, time: .current_virtual_time}'
```

- 调度器已使用稳定排序保证确定性；出现乱序意味着上游 `MarketDataReplaySource` 未按版本号过滤。
- 复查 `market_data_paths` 与 `data_source_profile` 是否能定位到某一发布版的切分文件。

### 3.3 重复 Bar

`MarketBar` 通过 `(symbol, timeframe, market_data_time, data_source_version, as_of_version)` 五元组去重。出现重复通常意味着上游切换数据源时未刷新 `as_of_version`。

修复路径：升级数据接入脚本，确保切源时 `as_of_version` 推进。

### 3.4 修订版本

`source_revision` 在被覆写为新版数据时，scheduling 必须按版本隔离两条事件链。
- 检查 `event_chain.jsonl` 中同一 `(symbol, market_data_time)` 的 `MarketBarClosed` 记录条数；
- > 1 即命中 BAR_REVISION 修复链路，建议截断该 run_id 并停止下游评论。

## 4. 事后

1. 在 `docs/decisions/open-questions.md` 追加本次具体现象与最终结论。
2. 仅当 `MISSING_BAR`、`OUT_OF_ORDER_BAR`、`DUPLICATE_BAR` 连续两个基准运行均为 0 时，将 runbook 链路重新启用。
3. 若发现 P1 告警（见 `backtest-observability.md` §5.1），触发 `pause_interpretation` 流程。

## 5. 相关文档

- 架构：`docs/architecture/backtest-testing-strategy.md` §6 Data Quality
- 可观测性：`docs/architecture/backtest-observability.md` §5 Alerting
