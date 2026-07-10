# Runbook: 回测报告解读

> 适用文档：`docs/architecture/testing-and-evaluation.md` 第 6 节。

本指南说明如何阅读产出的 backtest 报告，避免把回测结果误读为收益承诺。

## 1. 报告入口

每次 backtest 都会在 `output_dir` 下生成 `manifest.json` + 报告集。报告集中常用条目：

| 文件 | 内容 |
| --- | --- |
| `report.html` / `report.md` | 总览报告 |
| `signals.jsonl` | 本次 run 产生的全部 SignalEvent |
| `evaluations.jsonl` | 三重障碍、MFE/MAE 评价明细 |
| `event_chain.jsonl` | 完整 bar→signal→fill→evaluation 事件链 |

## 2. 阅读顺序

1. **Manifest 摘要**：`run_id`、`run_status`、`duration_seconds`、各 `total_*` 计数。
2. **数据质量**：`missing_bar_count`、`duplicate_bar_count`、`out_of_order_bar_count`、warnings。
3. **信号流水线**：`signals_generated_total` 与 `signals_rejected_total` 的比例。
4. **执行链路**：`orders_accepted_total / orders_total` 与 `t+1_blocked_total`。
5. **评价输出**：Net Return 分布、Hit Rate、MFE/MAE ratio、三重障碍 label 统计。

## 3. 解读约束

- 报告中所有收益数字**仅供策略对比使用**：
  - 不代表未来收益；
  - 不代表真实交易可获得收益（不含隔夜滑点、行情断流等）；
  - 在参数估计期内会包含 **前视偏差风险**，必须配合 replay-golden 双重验证。
- 评价字段 `time_to_mfe_seconds`、`triple_barrier_label` 用于策略结构诊断，**不要**直接当作"持仓时长指引"。
- `cost_model_version` 必须与回测使用的成本模型一致，否则净收益失真。
- 当运行状态为 `failed` / `partial` / `cancelled` 时，不要以部分结果得出策略结论。

## 4. 常见误读举例

| 误读 | 正确做法 |
| --- | --- |
| Net Return 高 ⇒ 准备实盘 | Net Return 是历史；上线前需 shadow 运行 ≥ 30 天 |
| Signal 多 ⇒ 策略好 | 看 Hit Rate 与盈亏比 |
| MFE 高 ⇒ 收益高 | MFE 仅表示最佳可达收益，需结合 MAE 与执行率 |
| Triple Barrier +1 占比高 ⇒ 策略好 | 必须配合 Period 长度与 hit ratio 综合判读 |

## 5. 交付前自检

- [ ] 报告中的 `deterministic_check_passed = true`
- [ ] `expected_assertions` 全部 `passed = true`
- [ ] 当前版本与上一黄金用例（`make test-replay-golden`）一致
- [ ] alert 列表为空或仅含已豁免项
- [ ] 报告已 attach 到对应 run_id 的工单
