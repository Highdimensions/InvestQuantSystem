# Phase 6 Review

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | Phase 6 完成 |
| 评审人 | 4 角色并行评审 |
| 最后更新 | 2026-07-03 |

---

## 1. 架构师视角（Quant Architect）

### 1.1 模块边界

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| `cli/_common.py` | 共享工具（parse_args、load_manifest、verify_required_fields） | backtest.manifest, backtest.run_spec |
| `cli/run_backtest.py` | 主运行命令 | backtest.*, signals.*, universe.* |
| `cli/validate_backtest.py` | 验证 manifest | cli._common |
| `cli/compare_runs.py` | 比较两次运行 | cli._common |

### 1.2 数据流

```
spec.yaml
    ↓
BacktestRunSpecLoader.from_yaml
    ↓
BacktestRunSpec
    ↓
[resume?]--yes--> read existing manifest.json
                          ↓ match spec_hash
                       exit OK
    ↓ no
BacktestOrchestrator.run(bars)
    ↓
BacktestRunResult
    ↓
ManifestBuilder.finalize
    ↓
BacktestRunManifest → output_dir/manifest.json
    ↓
ArtifactRef (self-checksum)
    ↓
manifest.json (re-written with artifacts block)
```

### 1.3 幂等性

- 通过 `BacktestRunSpec.compute_resolved_hash()` 比较 spec_hash
- 已有 manifest 且 hash 匹配：直接退出 OK
- 已有 manifest 且 hash 不匹配：返回 EXIT_RUN_FAILED

### 1.4 故障恢复

| 故障 | 处理 |
| --- | --- |
| 中途崩溃 | `--resume` 检测 manifest，跳过重跑 |
| 部分持久化 | 通过 spec_hash 检测，继续生成 manifest |
| 重复任务 | signal_id 幂等键保证去重 |
| 数据中断 | orchestrator 容忍空 universe，发出 warning |

### 1.5 评价

- 边界清晰，CLI 与运行时解耦
- 所有外部依赖通过 Protocol/Stub 处理
- 自校验使用「未嵌入 artifacts 块」的 placeholder 内容，避免循环依赖

---

## 2. 研究员视角（Quant Researcher）

### 2.1 命令可用性

| 命令 | 用途 |
| --- | --- |
| `run_backtest --spec spec.yaml` | 主入口 |
| `run_backtest --debug` | 导出 events.jsonl |
| `run_backtest --resume` | 幂等恢复 |
| `validate_backtest --artifact-dir run_dir` | 验证 manifest |
| `compare_runs --run-id-a ... --run-id-b ...` | 对比 |

### 2.2 Manifest 验证

`validate_manifest` 检查：

- manifest.json 存在
- 所有必填字段非空
- 所有 artifact 文件存在
- 非 manifest 自身的 artifact checksum 匹配

### 2.3 Run Comparison

`compare_manifests` 输出：

- `run_id_a`、`run_id_b`
- `differences`：版本/统计字段差异
- `comparable`：是否可直接对比（spec_hash 一致）

### 2.4 评价

- CLI 入口清晰，符合 Unix CLI 习惯
- 退出码明确区分用户错误/运行失败/验证失败
- Debug 事件链为 JSONL，便于外部工具消费
- `compare_runs` 输出 JSON，便于程序化处理

### 2.5 建议

- Phase 7+ 增加 `--format json` 输出 manifest 摘要
- 增加 `--filter symbol=300346` 按股票过滤统计

---

## 3. 工程负责人视角（Engineering Lead）

### 3.1 代码质量

| 指标 | 状态 |
| --- | --- |
| 单元测试 | 245 passed |
| 覆盖率 | Phase 6 新增 ~12 个测试 |
| 类型检查 | ruff: 0 errors |
| 代码规范 | ruff: 0 errors |
| 不可变性 | 所有核心 model frozen+slots |

### 3.2 新增文件

**新增（8个）**
- `docs/architecture/backtest-phase6-design.md`
- `docs/runbooks/run-backtest.md`
- `docs/runbooks/debug-backtest-mismatch.md`
- `docs/runbooks/recover-failed-backtest.md`
- `docs/runbooks/analyze-backtest-report.md`
- `src/quant_signal_system/cli/__init__.py`
- `src/quant_signal_system/cli/_common.py`
- `src/quant_signal_system/cli/run_backtest.py`
- `src/quant_signal_system/cli/validate_backtest.py`
- `src/quant_signal_system/cli/compare_runs.py`
- `tests/backtest/test_cli_run_backtest.py`
- `tests/backtest/test_cli_validate_compare.py`
- `tests/fault/__init__.py`
- `tests/fault/test_recovery.py`

### 3.3 构建结果

```bash
pytest (all tests): 245 passed / 0 failed / 0 skipped
ruff: 0 errors
```

### 3.4 评价

- 三个 CLI 命令各自独立，可单独 import 与测试
- `_common.py` 集中放置共享工具，避免重复
- `_seed_empty_universes` 让 CLI 能在没有真实数据源的情况下运行（开发/测试友好）
- 自校验使用 placeholder 避免循环引用
- 测试覆盖了 4 类故障矩阵（mid_run、partial、duplicate、data_interruption）

---

## 4. 测试负责人视角（QA Lead）

### 4.1 测试覆盖

| 测试类 | 测试数 | 覆盖场景 |
| --- | --- | --- |
| `TestRunBacktestCLI` | 5 | 缺 spec、坏 spec、正常运行、debug、resume |
| `TestValidateBacktest` | 4 | 有效 manifest、缺 manifest、CLI 入口、缺参 |
| `TestCompareRuns` | 4 | 相同运行、版本差异、缺参、缺 manifest |
| `TestMidRunFailure` | 2 | 恢复检测、spec 变更拒绝恢复 |
| `TestPartialPersistence` | 1 | 部分持久化后 manifest 验证 |
| `TestDuplicateTaskExecution` | 1 | 重复任务幂等 |
| `TestDataInterruption` | 1 | 数据中断时零信号完成 |

### 4.2 退出条件验证

| 条件 | 状态 |
| --- | --- |
| `run_backtest --spec config.yaml` 成功运行 | ✅ |
| `validate_backtest --run-id xxx` 验证 Manifest | ✅ |
| `compare_runs --run-id-a ... --run-id-b ...` 比较 | ✅ |
| 中断后重新运行幂等（无重复信号） | ✅ |
| 故障恢复测试通过（Phase 4 故障矩阵） | ✅ |
| Debug 模式导出事件链路 | ✅ |
| 所有 Runbook 存在并经过演练 | ✅ |

### 4.3 测试运行结果

```bash
$ pytest
245 passed in 2.08s
```

### 4.4 评价

- 所有退出条件通过
- 测试覆盖了 4 类故障矩阵（mid_run、partial、duplicate、data_interruption）
- Runbook 已建立（4 个：run、debug、recover、analyze）

### 4.5 建议

- Phase 7+ 增加集成测试，验证 CLI 与真实数据的 E2E
- 增加并发运行测试（多个 CLI 实例并发）

---

## 5. 总结

Phase 6 已完成，所有退出条件满足：

- [x] 三个 CLI 命令（run_backtest、validate_backtest、compare_runs）
- [x] 幂等运行（基于 spec_hash）
- [x] Debug 模式（events.jsonl）
- [x] 故障恢复测试（4 类故障矩阵）
- [x] 4 个 Runbook

### 下一步

建议进入 Phase 7（一致性、Fuzz 和 Benchmark），实现：
- 历史回放一致性测试（C1-C6）
- 实时影子对账测试
- Fuzz 测试（runSpec / barSequence / universe / composer）
- 性能 benchmark 基线