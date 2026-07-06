# Runbook: 分析回测报告

## 1. 读取报告

```bash
cat artifacts/runs/run_001/report.md
```

报告包含以下章节：

1. **Summary**：运行摘要（run_id、时间范围、信号数）
2. **Portfolio Metrics**：组合层指标（收益、Sharpe、回撤）
3. **Signal Metrics by Bucket**：信号层指标（按 strategy/symbol/direction 分桶）
4. **Warnings**：所有 RunWarning 列表

## 2. 检查必要字段

| 字段 | 来源 |
| --- | --- |
| run_id | manifest.json |
| strategy_versions | manifest.json |
| from_time / to_time | manifest.json |
| sample_count | report.md |
| unexecutable_count | report.md |
| warnings | manifest.json |

## 3. 常见分析问题

### 3.1 样本量过小

- 调大 from_time / to_time 范围
- 增加 universe symbols
- 检查 `unexecutable_count` 是否过高

### 3.2 命中率异常

- 检查 strategy 参数哈希（parameter_hash）
- 检查 signal/evaluation 版本

### 3.3 最大回撤过大

- 检查 PortfolioMetrics 的 final_value
- 确认 cost_model / fill_model 设置正确

## 4. 与历史对比

```bash
python -m quant_signal_system.cli.compare_runs \
  --run-id-a run_baseline \
  --run-id-b run_experiment \
  --artifact-dir artifacts/runs
```

输出 JSON 中：

- `comparable = true`：两次运行可直接对比
- `comparable = false`：spec_hash 不同，需要重新生成基线