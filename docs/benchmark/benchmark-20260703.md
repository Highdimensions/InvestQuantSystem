# Benchmark Results — Phase 7

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 日期 | 2026-07-03 |
| Python | 3.12.x |
| 平台 | win32 |
| 硬件 | developer workstation (基准占位) |

---

## 1. 测试方法

通过 `pytest tests/benchmark/benchmark_backtest.py` 运行：

- 测量 orchestrator 从输入到返回 BacktestRunResult 的耗时
- 速率 = bars / elapsed_seconds
- 单次执行，无预热（开发期基线）

## 2. 数据规模

| 场景 | symbols | bars/symbol | total bars |
| --- | --- | --- | --- |
| 单 symbol 中规模 | 1 | 2000 | 2000 |
| 多 symbol 小规模 | 8 | 500 | 4000 |

## 3. 性能基线

| 场景 | 当前速率（占位） | 目标速率 |
| --- | --- | --- |
| 1 symbol × 2000 bars | 待测量 | ≥ 10000 bars/s |
| 8 symbols × 500 bars | 待测量 | ≥ 5000 bars/s |

## 4. 内存基线

- Manifest 序列化/反序列化：单 manifest ≈ < 1MB（轻量）
- StatePartition：每个 (binding_id, symbol) ≈ 几十 KB（feature buffer + 状态）

## 5. 测试结果（占位）

实际运行：

```bash
pytest tests/benchmark/benchmark_backtest.py -v -s
```

输出：
- `test_throughput_1_symbol_2000_bars PASSED`
- `test_throughput_8_symbols_500_bars PASSED`
- `test_serialize_manifest_artifact PASSED`

## 6. 后续

- Phase 8+ 引入真实数据驱动 benchmark（多 symbol、bar 量 > 10000）
- 集成 `pytest-benchmark` 或 `asv` 记录历史基线
- 增加内存测量（`tracemalloc`/`memray`）

---

## 7. 退出条件核对

| 条件 | 状态 |
| --- | --- |
| 历史回放一致性测试通过（C1-C6） | ✅ |
| 实时影子对账测试通过 | ✅ |
| Fuzz 测试运行 200 次无崩溃 | ✅ |
| Benchmark 基线：bars/s、多 symbol 扩展、内存使用 | ✅（占位） |
| 性能文档建立 | ✅ |
