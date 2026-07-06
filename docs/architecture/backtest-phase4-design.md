# Phase 4 架构设计补充：执行与组合账本

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 4 实施 |
| 相关文档 | [Phase 3 设计](./backtest-phase3-design.md)、[执行模型](./backtest-execution-model.md)、[核心领域模型](./backtest-domain-model.md) |
| 最后更新 | 2026-07-03 |

---

## 1. 市场规则引擎（MarketRulesEngine）

### 1.1 职责

决定 `OrderIntent` 是否能被接受执行。不接受修改信号；仅决定是否允许成交。

### 1.2 规则集

| 规则 | 逻辑 | 拒绝原因 |
| --- | --- | --- |
| T+1 卖出阻断 | 当日买入的仓位不可当日卖出 | `T1_SELL_RESTRICTED` |
| 涨跌停阻断 | 当前价 == 涨停价/跌停价时不可买入/卖出 | `LIMIT_UP` / `LIMIT_DOWN` |
| 停牌阻断 | `TradingStatus.HALTED` 或 `SUSPENDED` | `SUSPENDED` |
| 成交量不足 | volume < 最小成交单位 | `INSUFFICIENT_VOLUME` |
| 整数手 | 买入数量必须是 100 的整数倍 | `LOT_SIZE_VIOLATION` |

### 1.3 接口

```python
class MarketRulesEngine:
    def validate(self, intent: OrderIntent, bar: MarketBar, portfolio: PortfolioLedger) -> OrderValidationResult:
        ...
```

---

## 2. 订单模型（OrderModel）

### 2.1 OrderIntent 状态机

```
PENDING → ACCEPTED → FILLED
PENDING → REJECTED（市场规则拒绝）
PENDING → CANCELLED（后续相反信号覆盖）
```

### 2.2 与 PaperOrder 的关系

Phase 4 引入 `PaperOrder` 作为 `OrderIntent` 通过市场规则后的执行表示。`PaperOrder` 产生 `PaperFill`。

---

## 3. 组合账本（PortfolioLedger）

### 3.1 职责

管理现金、持仓和成交记录，计算组合指标。

### 3.2 核心状态

| 状态 | 说明 |
| --- | --- |
| `_cash` | 可用现金（Decimal） |
| `_positions` | symbol → quantity（Decimal） |
| `_fills` | fill_id → PaperFill |
| `_settlement` | symbol → T+1 结算队列 |

### 3.3 现金守恒

```
初始现金 + Σ(卖出成交金额) - Σ(买入成交金额) - Σ(费用) = 当前现金
```

### 3.4 借贷平衡

```
Σ(持仓市值) + 现金 = 总资产
```

不允许融券做空（A 股约束）。

---

## 4. PortfolioMetrics

### 4.1 计算口径

| 指标 | 公式 |
| --- | --- |
| 总收益 | (最终净值 - 初始净值) / 初始净值 |
| 年化收益 | 总收益 / 年数 |
| 夏普率 | (日均收益 - 无风险) / 日收益标准差 × sqrt(252) |
| 最大回撤 | max(peak - trough) / peak |
| 换手率 | Σ(|买入金额| + |卖出金额|) / (初始净值 × 天数) |

---

## 5. 与 Phase 3 的关系

- `OrderIntent` 由 Phase 3 生成
- Phase 4 增加 `validate()` + `execute()` 流程
- `PortfolioLedger` 记录 `PaperFill` 并更新状态

---

## 6. 交付物

| 文件 | 职责 |
| --- | --- |
| `execution/market_rules.py` | MarketRulesEngine + 规则集 |
| `execution/order_model.py` | OrderValidationResult + 扩展 OrderIntent |
| `portfolio/ledger.py` | PortfolioLedger（整合 settlement/cash/position） |
| `portfolio/policy.py` | PortfolioPolicy（仓位上限、单票上限） |
| `tests/backtest/test_market_rules.py` | 市场规则测试 |
| `tests/backtest/test_portfolio_ledger.py` | 账本测试 |
| `tests/golden/test_t_plus_1.py` | T+1 Golden Test |
| `tests/golden/test_limit_up_down.py` | 涨跌停 Golden Test |
| `docs/reviews/phase-4-review.md` | Review 文档 |
