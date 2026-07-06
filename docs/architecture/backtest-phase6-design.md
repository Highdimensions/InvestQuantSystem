# Phase 6 架构设计补充：CLI 与恢复

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 6 实施 |
| 相关文档 | [Phase 5 设计](./backtest-phase5-design.md)、[Manifest 设计](./backtest-manifest-design.md)、[执行模型](./backtest-execution-model.md) |
| 最后更新 | 2026-07-03 |

---

## 1. CLI 入口

### 1.1 命令列表

| 命令 | 入口 | 职责 |
| --- | --- | --- |
| `run_backtest` | `cli.run_backtest:cli` | 运行回测，生成 manifest + 产物 |
| `validate_backtest` | `cli.validate_backtest:cli` | 验证 manifest 完整性和一致性 |
| `compare_runs` | `cli.compare_runs:cli` | 比较两次运行的 manifest 差异 |

### 1.2 `run_backtest` 命令

```bash
python -m quant_signal_system.cli.run_backtest --spec config.yaml [--output-dir artifacts/runs]
```

**参数：**
- `--spec`（必需）：BacktestRunSpec YAML 文件路径
- `--output-dir`（可选）：覆盖 spec 中的 output_dir
- `--debug`：启用 debug 模式，导出事件链路
- `--resume`：尝试从已存在的 run 恢复

**退出码：**
- 0：成功
- 1：用户错误（spec 解析失败）
- 2：回测失败（manifest 标记为 failed）
- 3：产物验证失败

### 1.3 `validate_backtest` 命令

```bash
python -m quant_signal_system.cli.validate_backtest --run-id run_001 --artifact-dir artifacts/runs/run_001
```

**检查项：**
1. manifest.json 存在且可解析
2. 所有 ArtifactRef 指向的文件存在
3. 所有 ArtifactRef 的 checksum_sha256 匹配
4. 必填字段非空（run_id、from_time、to_time、strategy_versions 等）
5. 数据版本格式正确

### 1.4 `compare_runs` 命令

```bash
python -m quant_signal_system.cli.compare_runs --run-id-a run_001 --run-id-b run_002
```

**输出：**
- 共同版本字段（确认是否可比）
- 差异字段（spec_hash、time_range 等）
- signal 数量对比
- metric 差异（如果 manifest 包含）

---

## 2. 幂等运行（Idempotency）

### 2.1 幂等键

| 键 | 来源 |
| --- | --- |
| run_id | BacktestRunSpec 显式提供或由 resolved_hash 前 8 位生成 |
| spec_hash | BacktestRunSpec.compute_resolved_hash() |
| signal_id | 基于 signal_id_index + 自增 ID |

### 2.2 重复检测

启动 run_backtest 时检查：

1. `--resume` 模式下，查找 `{output_dir}/manifest.json`
2. 若存在，读取 manifest.run_id 和 spec_hash
3. 若 spec_hash 与当前匹配，跳过 bar 处理，仅生成报告

### 2.3 幂等保证

- SignalEvent 写入时使用 `signal_id = hash(binding_id + symbol + event_time)` 形式，保证可复现
- `signal_repository.append_signal` 检测重复 signal_id，抛出 `DuplicateSignalError`

---

## 3. 故障恢复

### 3.1 故障矩阵

| 故障类型 | 恢复策略 |
| --- | --- |
| 中途崩溃（OS kill / power loss） | `--resume` 跳过已处理 bar |
| 部分持久化（部分信号已落盘） | 从最近的 checkpoint 恢复 |
| 任务重复执行（并发/重试） | signal_id 幂等键保证唯一 |
| 数据中断（market_data 缺失） | quarantine_record_count + warning |

### 3.2 Checkpoint 模型

Manifest 中包含 `completed_bars_count`，CLI 检查此字段判断是否需要从断点恢复。

### 3.3 恢复流程

```
1. 读取 manifest.json（若存在）
2. 比较 spec_hash，若不同则报错（spec 已变更，不能恢复）
3. 读取 completed_bars_count
4. 重新加载 bars，跳过前 N 根
5. 从 N+1 根继续处理
6. 完成后更新 manifest.completed_at
```

---

## 4. Debug 模式

### 4.1 `--debug` 标志

启用后：
- 所有 RunWarning 打印到 stderr
- 每个 bar 处理后写入 `debug/events.jsonl`
- 包含：bar timestamp、symbols processed、signals created、decisions
- 每个 signal 的完整 decision chain

### 4.2 Debug 输出

```json
{"event": "bar_processed", "bar_time": "...", "symbols": [...]}
{"event": "signal_created", "signal_id": "...", "strategy": "..."}
{"event": "universe_change", "from_version": "v1", "to_version": "v2"}
```

---

## 5. Runbook

### 5.1 run-backtest.md

基本运行流程：
1. 准备 spec YAML
2. 运行 `python -m quant_signal_system.cli.run_backtest --spec spec.yaml`
3. 检查 exit code
4. 检查 manifest.json 状态

### 5.2 debug-backtest-mismatch.md

当回测结果与预期不符时：
1. 启用 `--debug` 重跑
2. 查看 `debug/events.jsonl`
3. 对照 debug 决策链与预期
4. 必要时启用 `--resume` 重跑验证幂等性

### 5.3 recover-failed-backtest.md

当运行失败时：
1. 检查 manifest.json 的 run_status
2. 若为 `failed`，使用 `--resume` 恢复
3. 若为 `partial`，手动检查 completed_bars_count

### 5.4 analyze-backtest-report.md

报告分析流程：
1. 读取 `report.md`
2. 检查 warnings 列表
3. 对比 PortfolioMetrics 与预期
4. 检查 SignalMetrics 的样本量

---

## 6. 与 Phase 5 的关系

- CLI 调用 ArtifactReportBuilder 生成产物
- Manifest 写入与 Phase 5 的 manifest.json 兼容
- 幂等性与 SignalRepository 已存在的去重逻辑一致

---

## 7. 交付物

| 文件 | 职责 |
| --- | --- |
| `cli/__init__.py` | CLI 模块入口 |
| `cli/run_backtest.py` | 主运行命令 |
| `cli/validate_backtest.py` | Manifest 验证 |
| `cli/compare_runs.py` | 运行比较 |
| `tests/backtest/test_cli_run_backtest.py` | CLI 测试 |
| `tests/fault/test_mid_run_failure.py` | 中途崩溃恢复 |
| `tests/fault/test_partial_persistence.py` | 部分持久化恢复 |
| `tests/fault/test_duplicate_task_execution.py` | 重复任务幂等 |
| `tests/fault/test_data_interruption.py` | 数据中断恢复 |
| `docs/runbooks/run-backtest.md` | 基本运行手册 |
| `docs/runbooks/debug-backtest-mismatch.md` | Debug 手册 |
| `docs/runbooks/recover-failed-backtest.md` | 恢复手册 |
| `docs/runbooks/analyze-backtest-report.md` | 报告分析手册 |
| `docs/reviews/phase-6-review.md` | Phase 6 Review |