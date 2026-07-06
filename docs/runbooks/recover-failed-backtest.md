# Runbook: 恢复失败回测

## 1. 故障排查

```bash
# 查看 manifest 状态
cat artifacts/runs/run_001/manifest.json | jq '.run_status, .completed_at, .duration_seconds'

# 查看警告
cat artifacts/runs/run_001/manifest.json | jq '.warnings'
```

## 2. 恢复策略

### 2.1 部分完成

manifest.run_status = `partial` 时：

1. 备份当前 output_dir
2. 删除 manifest.json（保留其他产物）
3. 用相同 spec 重新运行

### 2.2 中途崩溃

OS 杀进程或断电后：

1. 检查 manifest.json 是否存在
2. 若存在，使用 `--resume` 重跑（spec_hash 匹配时会跳过）
3. 若 spec_hash 不匹配，需修改 spec 或重新生成

### 2.3 数据中断

market data 缺失时：

1. 检查 manifest 的 `quarantine_record_count`
2. 检查 `warnings` 列表中的 `MISSING_BAR` warning
3. 确认数据源恢复后重新运行

## 3. 幂等性

SignalRepository 写入时基于 signal_id 去重，相同 signal 不会重复落盘。

可在 `--resume` 模式下安全重跑：

```bash
python -m quant_signal_system.cli.run_backtest --spec spec.yaml --resume
```

## 4. 失败恢复测试

参见 `tests/fault/test_recovery.py`：

- `TestMidRunFailure`：中途失败 + 恢复
- `TestPartialPersistence`：部分持久化
- `TestDuplicateTaskExecution`：重复任务幂等
- `TestDataInterruption`：数据中断