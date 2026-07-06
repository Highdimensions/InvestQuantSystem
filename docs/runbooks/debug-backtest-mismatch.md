# Runbook: 调试回测不匹配

## 1. 启用 debug 重跑

```bash
python -m quant_signal_system.cli.run_backtest --spec spec.yaml --debug --resume
```

debug 事件会写入 `output_dir/debug/events.jsonl`。

## 2. 查看事件

```bash
cat output_dir/debug/events.jsonl | jq -c '.event, .run_id, .total_bars, .signals_generated'
```

常见事件类型：

- `run_complete`：运行完成
- `bar_processed`：单根 bar 已处理
- `signal_created`：信号已创建
- `universe_change`：股票池变更

## 3. 比对两次运行

```bash
python -m quant_signal_system.cli.compare_runs \
  --run-id-a run_001 \
  --run-id-b run_002 \
  --artifact-dir artifacts/runs
```

## 4. 常见不匹配原因

| 现象 | 排查方向 |
| --- | --- |
| signal 数量不同 | 检查 universe / spec_version 差异 |
| bar 数量不同 | 检查 data_source_version |
| 时间范围不同 | 检查 from_time / to_time |
| 输出文件不同 | 检查 manifest 的 artifacts 列表 |