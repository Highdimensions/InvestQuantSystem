# 回测平台数据契约扩展

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 建议方案 |
| 适用范围 | 回测与量化研究平台 Phase 1-7 实施 |
| 相关文档 | [当前状态审计](../reviews/backtest-current-state-audit.md)、[目标架构](./backtest-target-architecture.md)、[核心领域模型](./backtest-domain-model.md)、[现有数据契约](./data-contracts.md) |
| 最后更新 | 2026-07-03 |

---

## 1. 概述

本文档定义回测平台新增数据契约，与现有契约（`MarketBar`、`SignalEvent`、`SignalEvaluation` 等）的关系，以及版本化和不可变性要求。

**原则**：

- 新增契约遵循现有模式：`frozen=True, slots=True`、五类时间字段、版本字段、校验规则
- 不修改现有契约的字段定义，只新增扩展字段
- 所有新增契约包含 `schema_version` 字段

---

## 2. 新增契约字段定义

### 2.1 UniverseSnapshot（新增）

对应文档 [backtest-domain-model.md](./backtest-domain-model.md) 第 2 节。

```python
@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    schema_version: str = "universe-snapshot-v1"

    # 标识
    universe_id: str
    universe_version: str

    # 时间语义
    effective_time: datetime
    available_at: datetime

    # 内容
    symbols: tuple[str, ...]
    inclusion_reason: str          # "index_constituent" | "sector_classification" | "manual"
    source: str                   # "CSI" | "SSE" | "SZSE" | "manual"
    source_version: str

    # 修订追踪
    revision_id: str
    as_of_version: str
    replaced_by: str | None

    # 元数据
    created_at: datetime
    description: str = ""
```

**与现有契约的关系**：

- 复用 `AsOfDataset`（`contracts/reference_data.py`）的 as-of 语义验证逻辑
- 复用 `available_at` / `effective_time` 字段语义

### 2.2 StrategyBinding（新增）

对应文档 [backtest-domain-model.md](./backtest-domain-model.md) 第 3 节。

```python
@dataclass(frozen=True, slots=True)
class StrategyBinding:
    schema_version: str = "strategy-binding-v1"

    # 标识
    binding_id: str
    strategy_name: str
    strategy_version: str
    parameter_hash: str

    # 绑定关系
    universe_id: str
    universe_version: str

    # 版本
    feature_version: str
    composer_policy: str         # ConflictPolicy 枚举值
    market_rule_version: str | None
    cost_model_version: str
    fill_model_version: str

    # 权重
    weight: Decimal = Decimal("1.0")

    # 生效时间
    valid_from: datetime | None
    valid_to: datetime | None

    # 元数据
    description: str = ""
    yaml_path: Path | None = None
```

**与现有契约的关系**：

- `strategy_name` / `strategy_version` / `parameter_hash` 与 `StrategySpec.identity_key` 对齐
- `feature_version` 与 `FeatureSnapshot.feature_version` 对齐
- `cost_model_version` / `fill_model_version` 与 `SignalEvaluation` 中的对应字段对齐

### 2.3 BacktestRunSpec（新增）

对应文档 [backtest-domain-model.md](./backtest-domain-model.md) 第 4 节。

```python
@dataclass(frozen=True, slots=True)
class BacktestRunSpec:
    schema_version: str = "backtest-run-spec-v1"

    # 运行标识
    run_id: str                  # SHA256(original_yaml + git_commit + timestamp)
    run_mode: str = "backtest"  # "backtest" | "replay" | "shadow"

    # 时间范围
    from_time: datetime
    to_time: datetime
    timeframe: str = "1m"

    # 数据来源
    data_source_profile: DataSourceProfile   # 复用现有契约
    data_source_version: str
    as_of_version: str
    market_data_paths: tuple[str, ...] = field(default_factory=tuple)

    # 策略绑定
    strategy_bindings: tuple[StrategyBinding, ...]

    # 评价政策
    evaluation_policies: tuple[EvaluationPolicy, ...]   # 复用现有契约

    # 组合政策
    portfolio_policy: PortfolioPolicy | None = None      # 新增（Phase 4）
    initial_cash: Decimal = Decimal("1000000")
    cost_model_version: str
    fill_model_version: str

    # 市场规则
    market_rule_version: str | None = None

    # 时钟与确定性
    clock_policy: str = "frozen"
    random_seed: int | None = None

    # 存储与输出
    output_dir: Path
    store_signals: bool = True
    store_orders: bool = True
    store_fills: bool = True
    store_positions: bool = True
    store_evaluations: bool = True
    store_manifest: bool = True

    # 环境信息
    git_commit: str
    python_version: str
    platform: str

    # Resolved（运行时生成）
    resolved_config_hash: str | None = None
    universe_snapshots: tuple[UniverseSnapshot, ...] = field(default_factory=tuple)
```

**与现有契约的关系**：

- `data_source_profile` → 复用 `DataSourceProfile`
- `evaluation_policies` → 复用 `EvaluationPolicy`
- `run_id` → 与 `SignalEvent.signal_id` 无关联，但与 `SignalEvaluation.evaluation_run_id` 类似
- `git_commit` / `python_version` / `platform` → 与 `StrategyVersion.code_version` 对齐

### 2.4 ComposerDecision（新增）

对应文档 [backtest-domain-model.md](./backtest-domain-model.md) 第 5 节。

```python
@dataclass(frozen=True, slots=True)
class ComposerDecision:
    schema_version: str = "composer-decision-v1"

    # 标识
    decision_id: str             # SHA256(binding_id + market_data_time + candidates_json)
    signal_event_id: str | None   # 若有胜者
    binding_id: str
    symbol: str
    market_data_time: datetime

    # 候选
    candidates: tuple[ComposerCandidate, ...]

    # 决策
    policy: str                  # ConflictPolicy 枚举值
    decision: str               # "WINNER_SELECTED" | "ABSTAIN" | "ABSTAIN_ALL" | "ERROR"
    winner: ComposerCandidate | None

    # 版本
    composer_version: str
    decision_rule_version: str

    # 时间
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class ComposerCandidate:
    strategy_name: str
    strategy_version: str
    parameter_hash: str
    runtime_name: str
    direction: int
    signal_action: str
    score: Decimal
    confidence: Decimal
    reason_codes: tuple[str, ...]
    is_winner: bool
    rejection_reason: str | None
    rejection_detail: str | None
    candidate_snapshot: str       # JSON 序列化，用于审计
```

**与现有契约的关系**：

- `ComposerCandidate` 的 `strategy_name` / `strategy_version` / `parameter_hash` 与 `SignalCandidate` 对齐
- `direction` / `signal_action` 与 `SignalCandidate` 对齐
- `ComposerDecision.signal_event_id` 引用 `SignalEvent.signal_id`

### 2.5 OrderIntent（新增）

对应文档 [backtest-domain-model.md](./backtest-domain-model.md) 第 6 节。

```python
@dataclass(frozen=True, slots=True)
class OrderIntent:
    schema_version: str = "order-intent-v1"

    # 标识
    intent_id: str
    signal_id: str
    binding_id: str
    portfolio_id: str

    # 意向内容
    symbol: str
    side: str                  # "BUY" | "SELL"
    quantity: Decimal
    reference_price: Decimal

    # 时间语义
    intent_time: datetime
    executable_time: datetime
    market_data_time: datetime

    # 执行层填充
    status: str = "PENDING"     # "PENDING" | "ACCEPTED" | "REJECTED" | "CANCELLED"
    rejection_reason: str | None = None
    accepted_quantity: Decimal | None = None
    fill_price: Decimal | None = None
    fill_time: datetime | None = None
    fee: Decimal | None = None
    slippage: Decimal | None = None

    # 版本
    market_rule_version: str
    fill_model_version: str
    cost_model_version: str
```

**与现有契约的关系**：

- `signal_id` → 引用 `SignalEvent.signal_id`
- `executable_time` → 与 `SignalEvent.executable_time` 对齐
- `status=ACCEPTED` 时，生成 `PaperOrder`
- `fill_price` / `fee` / `slippage` → 与 `PaperFill` 对齐

### 2.6 BacktestRunManifest（新增）

对应文档 [backtest-domain-model.md](./backtest-domain-model.md) 第 7 节。

```python
@dataclass(frozen=True, slots=True)
class BacktestRunManifest:
    schema_version: str = "backtest-run-manifest-v1"

    # 运行标识
    run_id: str
    run_mode: str
    run_status: str             # "success" | "failed" | "partial" | "cancelled"

    # 时间
    created_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None

    # 配置快照
    original_spec_yaml: str
    resolved_spec_yaml: str
    resolved_config_hash: str

    # 环境版本
    git_commit: str
    git_branch: str
    python_version: str
    platform: str

    # 核心版本
    strategy_versions: tuple[str, ...]
    feature_versions: tuple[str, ...]
    universe_versions: tuple[str, ...]
    data_source_version: str
    as_of_version: str
    calendar_version: str
    evaluation_policy_versions: tuple[str, ...]
    cost_model_version: str
    fill_model_version: str
    market_rule_version: str
    engine_version: str        # 新增

    # 数据范围
    from_time: datetime
    to_time: datetime
    timeframe: str

    # 运行时统计
    total_bars_processed: int
    total_bars_skipped: int
    total_signals_generated: int
    total_signals_rejected: int
    total_order_intents: int
    total_orders_accepted: int
    total_orders_rejected: int
    total_fills: int
    total_evaluations_completed: int
    total_evaluations_postponed: int
    peak_memory_mb: float | None

    # 警告
    warnings: tuple[RunWarning, ...]

    # 数据质量
    missing_bar_count: int
    duplicate_bar_count: int
    out_of_order_bar_count: int
    quarantine_record_count: int

    # 产物
    artifacts: tuple[ArtifactRef, ...]

    # 确定性
    deterministic_check_passed: bool
    deterministic_check_detail: str = ""

    # 断言
    expected_assertions: tuple[str, ...] = field(default_factory=tuple)
    assertion_results: tuple[AssertionResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RunWarning:
    warning_code: str
    severity: str                # "info" | "warn" | "error"
    message: str
    affected_symbols: tuple[str, ...] = field(default_factory=tuple)
    affected_time_range: tuple[datetime, datetime] | None = None
    count: int = 1


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_name: str
    artifact_path: str
    artifact_type: str           # "parquet" | "json" | "csv" | "md"
    record_count: int | None
    checksum_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AssertionResult:
    assertion_name: str
    passed: bool
    detail: str = ""
```

### 2.7 PortfolioMetrics（新增）

组合层评价指标，对应 Signal Evaluation（信号评价）和 Portfolio Backtest（组合回测）的分层。

```python
@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    schema_version: str = "portfolio-metrics-v1"

    # 标识
    run_id: str
    portfolio_id: str

    # 时间范围
    from_time: datetime
    to_time: datetime

    # 核心收益指标
    total_return: Decimal | None       # 总收益率
    annualized_return: Decimal | None  # 年化收益率（仅 time_range 允许时）
    volatility: Decimal | None        # 收益率波动率（年化）
    sharpe_ratio: Decimal | None      # 夏普比率（注明计算口径）
    max_drawdown: Decimal | None       # 最大回撤（绝对值）
    max_drawdown_pct: Decimal | None  # 最大回撤（百分比）
    drawdown_duration_days: int | None  # 最大回撤持续天数

    # 持仓与仓位
    avg_gross_exposure: Decimal | None  # 平均总仓位
    avg_net_exposure: Decimal | None    # 平均净仓位
    max_gross_exposure: Decimal | None
    max_net_exposure: Decimal | None
    cash_utilization_pct: Decimal | None

    # 交易统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal | None           # 胜率
    profit_factor: Decimal | None     # 盈利总额 / 亏损总额绝对值
    avg_win: Decimal | None
    avg_loss: Decimal | None
    largest_win: Decimal | None
    largest_loss: Decimal | None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 成本
    total_transaction_cost: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    total_stamp_tax: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")

    # 订单统计
    total_orders: int
    accepted_orders: int
    rejected_orders: int
    t_plus_1_blocked_count: int = 0
    limit_up_blocked_count: int = 0
    limit_down_blocked_count: int = 0
    suspended_blocked_count: int = 0

    # 按标的分桶
    symbol_metrics: tuple[SymbolMetrics, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SymbolMetrics:
    symbol: str
    total_trades: int
    total_return: Decimal | None
    avg_position_days: float | None
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
```

---

## 3. 与现有契约的关系矩阵

| 新契约 | 引用/被引用 | 关系类型 |
| --- | --- | --- |
| `UniverseSnapshot` | → `StrategyBinding.universe_id` | 引用（FK） |
| `StrategyBinding` | → `UniverseSnapshot.universe_id` | 被引用 |
| `StrategyBinding` | → `BacktestRunSpec.strategy_bindings` | 组成 |
| `BacktestRunSpec` | → `StrategyBinding` | 组成 |
| `BacktestRunSpec` | → `DataSourceProfile`（现有） | 复用 |
| `BacktestRunSpec` | → `EvaluationPolicy`（现有） | 复用 |
| `ComposerDecision` | → `SignalEvent.signal_id` | 引用（可空） |
| `ComposerDecision` | → `ComposerCandidate` | 组成 |
| `OrderIntent` | → `SignalEvent.signal_id` | 引用 |
| `OrderIntent` | → `PaperOrder`（现有） | 派生（ACCEPTED 时） |
| `OrderIntent` | → `PaperFill`（现有） | 派生（ACCEPTED 时） |
| `BacktestRunManifest` | → `BacktestRunSpec` | 快照 |
| `BacktestRunManifest` | → `ArtifactRef` | 组成 |
| `BacktestRunManifest` | → `RunWarning` | 组成 |
| `PortfolioMetrics` | → `BacktestRunManifest.run_id` | 引用 |

---

## 4. 版本化要求

### 4.1 新增版本字段汇总

| 契约 | 版本字段 | 来源 |
| --- | --- | --- |
| `UniverseSnapshot` | `schema_version`, `universe_version`, `as_of_version`, `source_version` | 新增 |
| `StrategyBinding` | `schema_version`, `parameter_hash`, `feature_version`, `cost_model_version`, `fill_model_version` | 新增 |
| `BacktestRunSpec` | `schema_version`, `data_source_version`, `as_of_version`, `resolved_config_hash` | 新增 |
| `ComposerDecision` | `schema_version`, `composer_version`, `decision_rule_version` | 新增 |
| `OrderIntent` | `schema_version`, `market_rule_version`, `fill_model_version`, `cost_model_version` | 新增 |
| `BacktestRunManifest` | `schema_version`, `resolved_config_hash`, `engine_version` | 新增 |
| `PortfolioMetrics` | `schema_version` | 新增 |

### 4.2 版本混用约束

以下版本组合必须在同一报告中保持一致：

```
同一 BacktestRunManifest 内：
  strategy_versions ≠ mixed across 报告分桶
  universe_versions ≠ mixed across 报告分桶
  data_source_version 必须单一
  as_of_version 必须单一
  evaluation_policy_versions 不得跨报告混合
  cost_model_version 不得跨报告混合
  fill_model_version 不得跨报告混合
  market_rule_version 不得跨报告混合
```

违反上述约束时，`manifest.json` 必须包含 `version_mismatch_warnings` 字段，并在报告首页展示。

---

## 5. 时间语义汇总

| 契约 | 时间字段 | 语义 |
| --- | --- | --- |
| `UniverseSnapshot` | `effective_time`, `available_at` | 成分生效时间 / 快照可见时间 |
| `StrategyBinding` | `valid_from`, `valid_to` | 绑定生效时间窗口 |
| `BacktestRunSpec` | `from_time`, `to_time` | 回测数据范围 |
| `BacktestRunManifest` | `created_at`, `completed_at` | 运行生命周期 |
| `ComposerDecision` | `decided_at`（虚拟时间） | 决策时间 |
| `OrderIntent` | `intent_time`, `executable_time`, `market_data_time` | 意向生成 / 可执行 / 信号时间 |

**已确定**：以上时间字段均以 UTC 存储，以 `market_local` 时区展示。

---

## 6. 校验规则

| 契约 | 校验规则 | 失败行为 |
| --- | --- | --- |
| `UniverseSnapshot` | `symbols` 非空；`effective_time <= available_at` | `InvalidUniverseError` |
| `StrategyBinding` | `weight >= 0`；`valid_from < valid_to`（若两者均非 None） | `InvalidBindingError` |
| `BacktestRunSpec` | `from_time < to_time`；`strategy_bindings` 非空 | `InvalidRunSpecError` |
| `ComposerDecision` | `candidates` 非空 | 记录 `ERROR` 决策 |
| `OrderIntent` | `quantity > 0` | `InvalidIntentError` |
| `BacktestRunManifest` | `run_id` 非空；`run_status` 为已知枚举 | 拒绝写入 |

---

## 7. Schema 演进策略

- 所有新增契约包含 `schema_version` 字段
- 新增字段优先保持向后兼容
- 删除或语义变更需新增 `schema_version`，并提供迁移说明
- 契约测试覆盖旧版本样本读取

---

## 8. 产物格式（契约层）

一次回测运行的标准产物：

| 文件名 | 格式 | 对应契约 | 状态 |
| --- | --- | --- | --- |
| `manifest.json` | JSON | `BacktestRunManifest` | 新增 |
| `signals.parquet` | Parquet | `SignalEvent` | 扩展现有 SQLite |
| `composer-decisions.parquet` | Parquet | `ComposerDecision` | 新增 |
| `order-intents.parquet` | Parquet | `OrderIntent` | 新增 |
| `fills.parquet` | Parquet | `PaperFill` | 复用 |
| `evaluations.parquet` | Parquet | `SignalEvaluation` | 复用 |
| `portfolio-metrics.json` | JSON | `PortfolioMetrics` | 新增 |
| `report.md` | Markdown | 派生报告 | 扩展 |
