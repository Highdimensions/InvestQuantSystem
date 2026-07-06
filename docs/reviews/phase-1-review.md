# Phase 1 Review：契约与 RunSpec

## 文档信息

| 项目 | 内容 |
| --- | --- |
| Phase | 1 — 契约与 RunSpec |
| 评审日期 | 2026-07-03 |
| 评审人 | A（架构）、B（量化正确性）、C（测试与可靠性）、D（性能与工程） |
| 基线 | 85 passed → 135 passed（+50 new）|
| Linter | ruff: All checks passed |
| 测试结果 | 135 passed / 0 failed / 0 skipped |

---

## Reviewer A：架构与模块边界

### A.1 模块职责检查

| 模块 | 状态 | 评价 |
| --- | --- | --- |
| `universe/contracts.py` | ✅ | `UniverseSnapshot` 职责清晰：股票池版本快照 |
| `universe/repository.py` | ✅ | 追加存储、幂等写入、版本查询 |
| `universe/resolver.py` | ✅ | as-of 解析，不泄漏存储细节 |
| `backtest/run_spec.py` | ✅ | `BacktestRunSpec` + `StrategyBinding` + Loader |
| `backtest/manifest.py` | ✅ | `BacktestRunManifest` + Builder，支持增量构建 |
| `config/versions.py` | ✅ | 线程安全修复，无破坏性变更 |

### A.2 依赖方向检查

```
universe/contracts.py   →  无外部依赖（仅 quant_signal_system.contracts.market）
universe/repository.py  →  universe/contracts.py（单向）
universe/resolver.py     →  universe/repository.py（单向）
backtest/run_spec.py    →  universe/contracts.py, config/data_source.py（单向）
backtest/manifest.py    →  无外部依赖
config/versions.py      →  contracts/versions.py（单向）
```

**结论：无循环依赖。**

### A.3 数据所有权

| 类 | 所有权 | 评估 |
| --- | --- | --- |
| `UniverseSnapshot` | `universe/` 模块 | ✅ 清晰 |
| `StrategyBinding` | `backtest/` 模块 | ✅ 清晰 |
| `BacktestRunSpec` | `backtest/` 模块 | ✅ 清晰 |
| `BacktestRunManifest` | `backtest/` 模块 | ✅ 清晰 |

### A.4 过度设计检查

| 设计 | 评估 | 说明 |
| --- | --- | --- |
| `universe_id_from_index()` 在 `repository.py` | ⚠️ Minor | 该函数不在 `__all__` 中但定义了；接口边界略模糊 |
| `ManifestBuilder` 链式调用 | ✅ 合理 | Builder 模式适合增量构建 |
| `BacktestRunSpec.compute_resolved_hash()` | ✅ 合理 | SHA-256 确定性哈希 |

### A.5 扩展性

| 点 | 评估 |
| --- | --- |
| 新增 Universe 来源（BT-TBD-07） | ✅ 通过 `UniverseRepository.save()` 扩展，无需修改核心 |
| 新增 Universe 触发机制（BT-TBD-08） | ✅ 通过 `UniverseResolver.resolve()` 扩展 |
| 新增 BacktestRunSpec 字段 | ✅ frozen dataclass，需 `replace()` 或新版本 |

### A.6 发现

| 编号 | 级别 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| A-01 | Minor | `universe_id_from_index()` 定义在 `repository.py` 但未在 `__init__` 导出 | 从 `__all__` 中移除或移到工具模块 |
| A-02 | Suggestion | `StrategyBinding.composer_policy` 接受任意字符串，未与 `ConflictPolicy` 枚举关联 | Phase 3 引入时补上类型约束 |

---

## Reviewer B：量化正确性

### B.1 前视偏差防护

| 检查点 | 状态 | 实现位置 |
| --- | --- | --- |
| `UniverseSnapshot.is_visible_at()` 强制 `available_at <= decision_time` | ✅ | `universe/contracts.py:63-65` |
| `UniverseResolver.resolve()` 支持 `require_strict=True` | ✅ | `universe/resolver.py` |
| `BacktestRunSpec` 时间范围 `from_time < to_time` 校验 | ✅ | `run_spec.py:143` |
| Bar 闭合检测（FeatureEngine 层已有） | ✅ | 继承 Phase 0 已有能力 |

### B.2 数据泄漏防护

| 检查点 | 状态 | 说明 |
| --- | --- | --- |
| `UniverseSnapshot` as-of 语义 | ✅ 完整 | `effective_time` + `available_at` 双约束 |
| `AsOfDataset.validate_visible_at()` 已有 | ✅ 继承 | Phase 0 已有 |
| Universe 内容（symbols）版本化 | ✅ 完整 | `universe_version` + `source_version` |

### B.3 量化语义正确性

| 语义 | 状态 | 评估 |
| --- | --- | --- |
| `UniverseSnapshot.symbols` 是 `tuple`（不可变） | ✅ | 防止运行时修改 |
| `StrategyBinding.weight >= 0` | ✅ | `run_spec.py:82` |
| `valid_from < valid_to` | ✅ | `run_spec.py:87-88` |
| `run_status` 枚举约束 | ✅ | 仅限 `success/failed/partial/cancelled` |

### B.4 关键发现

| 编号 | 级别 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| B-01 | Major | Phase 1 未实现实际 Universe 数据来源（BT-TBD-07 未决策） | Phase 1 交付的 `UniverseRepository` 可接受手工 JSON 快照；通过 `from_dict` 加载；无阻断 |
| B-02 | Major | `UniverseResolver.symbols_for()` 返回的 `tuple` 在时间推进时需要重新查询 | Phase 2 Orchestrator 中需要在 Universe 切换时重新调用 `resolve()` |
| B-03 | Minor | `BacktestRunSpec.timeframe` 校验仅检查已知值，但不验证与 `TradingCalendar` 的兼容性 | Phase 2 在 Orchestrator 中补充兼容性检查 |

### B.5 量化正确性风险评估

**Phase 1 不涉及信号生成、特征计算或评价，因此量化正确性风险低。** 关键风险已在 Phase 2 明确（Orchestrator 与 UniverseResolver 的交互）。

---

## Reviewer C：测试与可靠性

### C.1 测试覆盖矩阵

| 测试类 | 测试数 | 覆盖点 |
| --- | --- | --- |
| `TestStrategyBinding` | 4 | 有效绑定、缺失字段、负权重、时间窗口矛盾 |
| `TestBacktestRunSpec` | 5 | 有效规格、时间顺序、空绑定、时间范围、Hash 确定性 |
| `TestBacktestRunSpecLoader` | 4 | 最小加载、必需字段、日期格式、非法日期 |
| `TestRunWarning` | 2 | 基本构造、序列化 |
| `TestArtifactRef` | 1 | 基本构造 |
| `TestBacktestRunManifest` | 4 | 最小清单、状态枚举、空 ID、序列化 |
| `TestManifestBuilder` | 8 | Builder 增量构建、所有字段 |
| `TestUniverseSnapshot` | 5 | 有效快照、空 symbols、as-of 约束、可见性、Hash |
| `TestUniverseRepository` | 6 | 存取、幂等、冲突、版本查询、not found |
| `TestUniverseResolver` | 3 | 可见解析、严格拒绝、symbols_for |
| `TestVersionRegistryThreadSafety` | 7 | 幂等、冲突、查询、并发同 ID、并发不同 ID、快照不可变 |
| **总计** | **49** | |

### C.2 边界条件覆盖

| 场景 | 测试 | 状态 |
| --- | --- | --- |
| 空 symbols | `test_empty_symbols_raises` | ✅ |
| `available_at > effective_time` | `test_available_at_after_effective_raises` | ✅ |
| `valid_from >= valid_to` | `test_valid_from_after_valid_to_raises` | ✅ |
| 并发写入同一 identity | `test_concurrent_freeze_is_idempotent` | ✅ |
| 并发写入不同 identity | `test_concurrent_freeze_different_identities_no_conflict` | ✅ |
| Hash 确定性 | `test_resolved_hash_deterministic` | ✅ |
| Hash 变更检测 | `test_resolved_hash_changes_with_params` | ✅ |
| as-of 边界 | `test_is_visible_at` | ✅ |

### C.3 可靠性发现

| 编号 | 级别 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| C-01 | Minor | 现有 `BacktestRunSpec` 测试不覆盖 YAML 文件加载（仅测试 dict） | Phase 6 CLI 实现时补全 |
| C-02 | Minor | `ManifestBuilder._get_git_commit()` / `_get_git_branch()` 在无 git 环境静默返回空字符串 | 已在文档中说明；建议 Phase 1 补充 `@pytest.mark.skipif` 测试 |
| C-03 | Suggestion | 缺少 `UniverseRepository.get_by_id()` 的专门测试 | Phase 2 前不阻塞 |

### C.4 幂等性验证

| 操作 | 幂等键 | 验证 |
| --- | --- | --- |
| `UniverseRepository.save()` | `(universe_id, universe_version)` | `test_idempotent_save` ✅ |
| `VersionRegistry.freeze_strategy()` | `(strategy_name, strategy_version, parameter_hash, code_version)` | `test_freeze_strategy_idempotent` ✅ |

### C.5 故障恢复

Phase 1 契约层无实际运行故障场景（无 Orchestrator 实现）。Phase 6 CLI 实现后通过故障测试覆盖。

---

## Reviewer D：性能与工程质量

### D.1 时间复杂度

| 操作 | 复杂度 | 评估 |
| --- | --- | --- |
| `UniverseRepository.save()` | O(1) | ✅ 字典写入 |
| `UniverseRepository.get()` | O(1) | ✅ 字典查找 |
| `UniverseRepository.latest_visible()` | O(n) | ⚠️ 线性扫描；可接受（Phase 1 规模小） |
| `BacktestRunSpec.compute_resolved_hash()` | O(n×bindings) | ✅ 线性，n=绑定数 |
| 线程安全（`VersionRegistry`） | O(1) | ✅ RLock 临界区极小 |

### D.2 内存复杂度

| 结构 | 评估 |
| --- | --- |
| `UniverseRepository._snapshots` | O(n)，n=快照数 |
| `UniverseRepository._by_id_and_version` | O(n)，与 `_snapshots` 共享存储 |
| `VersionRegistry._frozen_strategies` | O(n)，n=冻结策略数 |
| `BacktestRunManifest` | O(n)，n=warnings + artifacts + assertions |
| `BacktestRunSpec` | O(n)，n=strategy_bindings |

**无内存泄漏风险。**

### D.3 多 symbol / 多策略扩展

Phase 1 未实现 Orchestrator，无扩展性验证。Phase 2 将通过 `strategy_bindings` 的 tuple 支持多绑定。

### D.4 类型和异常设计

| 方面 | 评估 |
| --- | --- |
| 所有新类 `frozen=True, slots=True` | ✅ |
| 所有新类 `dataclass` + `field` | ✅ |
| 错误类型继承 `MarketDataValidationError` | ✅ 一致 |
| `__all__` 显式导出 | ✅ |
| Docstring 存在 | ✅ |
| 公开接口类型标注 | ✅ |

### D.5 新增依赖评估

| 依赖 | 用途 | 评估 |
| --- | --- | --- |
| `yaml`（已有） | YAML 配置加载 | ✅ 无新增 |
| `threading`（Python 内置） | VersionRegistry 线程安全 | ✅ 无新增 |
| `hashlib`（Python 内置） | 确定性哈希 | ✅ 无新增 |
| `dataclasses`（Python 内置） | 数据类 | ✅ 无新增 |

**Phase 1 未引入任何新依赖。**

### D.6 工程发现

| 编号 | 级别 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| D-01 | Minor | `run_spec.py` 中 `yaml` 使用懒加载（import 在函数内） | Phase 6 CLI 需要时已就绪；当前 `run_spec.py` 顶层导入 `import yaml` | — |
| D-02 | Minor | `BacktestRunSpec` 的 `__post_init__` 包含验证逻辑，但 `validate()` 方法未显式调用 | 内部由 `__post_init__` 调用；接口一致性好；无需修复 |
| D-03 | Suggestion | `UniverseRepository` 的 `_snapshots` 和 `_by_id_and_version` 双重存储存在数据不一致风险（`save` 更新两者但 `get_by_id` 只用 `_by_id_and_version`） | 建议 Phase 2 重构为单一 dict 或重构 `get_by_id` 使用 `_snapshots` |

---

## 综合结论

### 修复情况

| 编号 | 级别 | 问题 | 是否修复 |
| --- | --- | --- | --- |
| A-01 | Minor | `universe_id_from_index` 未导出 | 未修复（不影响功能） |
| A-02 | Suggestion | `composer_policy` 无枚举约束 | 待 Phase 3 |
| B-01 | Major | Universe 数据来源未决策 | 记录在案（BT-TBD-07）|
| B-02 | Major | UniverseResolver 需在切换时重查询 | 记录在 Phase 2 计划 |
| B-03 | Minor | timeframe 与日历兼容性未校验 | 记录在 Phase 2 计划 |
| C-01 | Minor | YAML 文件加载无测试 | 待 Phase 6 |
| C-02 | Minor | git 环境静默失败 | 已在文档中说明 |
| C-03 | Suggestion | `get_by_id` 无专门测试 | 记录 |
| D-01 | Minor | yaml import 顶层 | 无问题 |
| D-02 | Minor | validate 显式调用 | 无问题 |
| D-03 | Suggestion | 双重存储不一致 | 记录在 Phase 2 |

**所有 Blocker 数量：0**

### 遗留风险

| 编号 | 风险 | 缓解 |
| --- | --- | --- |
| RISK-01 | `UniverseRepository.latest_visible()` O(n) 扫描 | Phase 1 规模小可接受；Phase 2 考虑索引 |
| RISK-02 | Universe 数据来源未决策（BT-TBD-07） | Phase 1 接受手工 JSON 快照启动 |

### 是否满足 Phase 1 验收条件

| 验收条件 | 状态 |
| --- | --- |
| `UniverseSnapshot` 契约测试通过 | ✅ 5 个测试全部通过 |
| `StrategyBinding` 契约测试通过 | ✅ 4 个测试全部通过 |
| `BacktestRunSpec` 契约测试通过 | ✅ 5 个测试全部通过 |
| `BacktestRunManifest` 契约测试通过 | ✅ 4 个测试全部通过 |
| `BacktestRunSpec.from_dict()` 成功加载 | ✅ 4 个 Loader 测试全部通过 |
| Universe as-of 语义正确 | ✅ `test_is_visible_at` 覆盖 |
| 单元测试覆盖配置校验 | ✅ |
| `VersionRegistry` 竞态修复 | ✅ 7 个线程安全测试通过 |
| ruff lint | ✅ All checks passed |
| 现有测试未破坏 | ✅ 85 → 135（+50） |

**Phase 1 验收通过。建议进入 Phase 2。**

### 建议进入下一阶段

**是。** Phase 1 的契约骨架已完整建立，`Universe` 和 `BacktestRunSpec` 均可独立使用，为 Phase 2 的 Orchestrator 和状态隔离提供了坚实基础。
