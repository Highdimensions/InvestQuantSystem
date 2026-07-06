# Runbook: 运行回测

## 1. 准备 spec YAML

最小 spec 示例：

```yaml
from_time: "2025-06-02T09:30:00+00:00"
to_time:   "2025-06-02T10:00:00+00:00"
timeframe: "1m"
data_source_version: "dv1"
as_of_version: "asof-v1"
output_dir: "artifacts/runs/run_001"
strategy_bindings:
  - binding_id: "b1"
    strategy_name: "rule_vol_breakout"
    strategy_version: "v1"
    parameter_hash: "ph1"
    universe_id: "u1"
    universe_version: "v1"
    feature_version: "f1"
```

## 2. 运行命令

```bash
python -m quant_signal_system.cli.run_backtest --spec spec.yaml
```

可选参数：

- `--output-dir`：覆盖 spec 中的 output_dir
- `--debug`：导出事件链路到 `debug/events.jsonl`
- `--resume`：幂等恢复

## 3. 检查退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（spec 解析失败、缺少 binding 等） |
| 2 | 回测失败（与现有 manifest 不匹配） |
| 3 | 产物验证失败 |

## 4. 检查 manifest

```bash
cat artifacts/runs/run_001/manifest.json | jq '.run_status, .total_signals_generated, .warnings'
```

## 5. 验证 manifest

```bash
python -m quant_signal_system.cli.validate_backtest --artifact-dir artifacts/runs/run_001
```