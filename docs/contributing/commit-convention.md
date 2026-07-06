# 提交信息规范（Commit Message Convention）

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 已确定 |
| 适用范围 | 本仓库所有 commit |
| 规范来源 | Conventional Commits v1.0.0 + Angular Contributor Guide 提炼 |
| 最后更新 | 2026-07-06 |

---

## 1. 设计原则

- 信息密度高，便于 `git log --oneline` 直接阅读
- 可程序化解析（自动生成 CHANGELOG、按 type 过滤日志、按 scope 聚合）
- Subject 与 body 分离，长度受控（Linux/Chromium 风格）
- 中文 vs 英文：subject 关键词固定为英文（`feat` / `fix` 等），其余正文保持中文

---

## 2. 整体结构

```
<type>(<scope>): <subject>            ← 必填，单行
                                       ← 空行
<body>                                 ← 选填，72 字/行
                                       ← 空行
<footer>                               ← 选填，BREAKING CHANGE / Refs / Closes
```

### 2.1 提交头（Header，必填）

格式：`<type>(<scope>): <subject>`

- 总长度 ≤ 72 个字符
- 不使用句号结尾
- 使用祈使语气（"add"，非 "added" 或 "adds"）
- subject 首字母不大写（保留名词专有名词例外）

### 2.2 正文（Body，选填）

- 解释「为什么改」而非「改了什么」
- 每行 ≤ 72 个字符
- 段落之间空一行
- 列举关键变更点或决策依据

### 2.3 页脚（Footer，选填）

- `BREAKING CHANGE: <description>` —— 描述不兼容变更与迁移路径
- `Refs: #123` 或 `Closes #456` —— 关联 issue / PR
- `Co-authored-by: Name <email>` —— 协同作者致谢

---

## 3. 允许的 type

| type | 含义 | CHANGELOG 段落 |
| --- | --- | --- |
| `feat` | 新增用户可见能力 | Features |
| `fix` | 修复 bug / 行为偏差 | Bug Fixes |
| `docs` | 仅文档（不影响代码） | Documentation |
| `refactor` | 内部重构，不变更行为 | Refactors |
| `perf` | 性能优化 | Performance |
| `test` | 仅测试 | Tests |
| `build` | 构建系统 / 依赖变更 | Build System |
| `ci` | CI 配置 / 脚本 | CI |
| `chore` | 工具链 / 元数据 | Chores |
| `revert` | 回滚之前提交 | Reverts |

**禁止 type**：`feat-add`、`feature`、`bug`、`misc`、`wip`（开发中请勿合并）。

---

## 4. scope 命名

scope 必须出现在下表内，便于聚合：

| 路径前缀 | scope 名称 |
| --- | --- |
| `src/quant_signal_system/backtest/` | `backtest` |
| `src/quant_signal_system/cli/` | `cli` |
| `src/quant_signal_system/strategies/` | `strategies` |
| `src/quant_signal_system/portfolio/` | `portfolio` |
| `src/quant_signal_system/execution/` | `execution` |
| `src/quant_signal_system/evaluation/` | `evaluation` |
| `src/quant_signal_system/reporting/` | `reporting` |
| `src/quant_signal_system/signals/` | `signals` |
| `src/quant_signal_system/universe/` | `universe` |
| `src/quant_signal_system/market_data/` | `market_data` |
| `src/quant_signal_system/time/` | `time` |
| `src/quant_signal_system/config/` | `config` |
| `tests/` | `tests` |
| `docs/` | `docs` |
| `Makefile` / `scripts/` / `pyproject.toml` | `build` |
| `.github/` / `.circleci/` 等 CI 文件 | `ci` |

跨多个 scope 时省略 scope：`feat: add end-to-end replay consistency test`，或在 subject 中点出最大权重的 scope：`feat(backtest,cli): add phase-6 cli commands`。

---

## 5. subject 写作模板

### 5.1 模板

```
<动词> <对象> [限定]
```

示例（推荐 → 反例）：

| ✅ 推荐 | ❌ 反例 | 问题 |
| --- | --- | --- |
| `feat(backtest): add orchestrator with closed-bar feature engine` | `feat: changes to backtest` | 太宽泛 |
| `fix(orchestrator): share VirtualClock with SignalService` | `Bug fix` | 无 type、无 scope |
| `refactor(manifest): split builder into dedicated methods` | `Refactor` | 不清晰 |

### 5.2 常用动词

| 动词 | 含义 |
| --- | --- |
| `add` | 新增 |
| `remove` / `drop` | 移除 |
| `update` / `change` | 修改既有逻辑 |
| `rename` | 重命名 |
| `move` | 移动 |
| `extract` | 抽取 |
| `split` / `merge` | 拆分 / 合并 |
| `freeze` / `lock` | 冻结 / 锁版本 |

---

## 6. body 写作模板

```
问题（Why）：
- 旧实现/旧文档存在什么不足

改动（What）：
- 关键模块 / 文件列表
- 关键决策（ADR 引用）

影响（Impact）：
- 对调用方、API、性能、可观测性的影响
```

每个段落用短横线 `-` 或数字 `1.` `2.`，避免过度列表化。

---

## 7. BREAKING CHANGE 表达

- 在正文最末独立段落写：

```
BREAKING CHANGE: <description of what breaks and migration path>
```

- 或在 type/scope 后加 `!`：`feat(api)!: remove legacy v1 signal ids`
- 任何 `!` 提交必须更新 `docs/decisions/backtest-open-questions.md` 和 CHANGELOG

---

## 8. 示例

### 8.1 feat

```
feat(backtest): add phase-7 consistency, fuzz and benchmark suites

问题：
- Phase 0–6 缺少跨运行的确定性回归保护
- orchestrator 与 SignalService 时钟不同步，长 bar 序列触发 MarketDataValidationError

改动：
- 引入 shared-clock 测试 harness（tests/helpers/orchestration.py）
- BacktestOrchestrator 接受可选 clock 并把同一实例注入 feature_engine
- 新增 79 个测试覆盖 replay 一致性、shadow 对账、随机输入鲁棒性与基线 benchmark

影响：
- 324 测试全通过，ruff 0 errors
- 修复隐藏的接线 bug，但保留 BacktestOrchestrator 默认行为
- benchmark 仅作占位，下一 Phase 用真实数据复测
```

### 8.2 fix

```
fix(orchestrator): share VirtualClock with SignalService and feature engine

问题：
- SignalService.clock 永远停留在 from_time，导致 event_time < market_data_time
- RollingFeatureEngine 默认使用 SystemClock（墙钟），feature_snapshot.generated_at > event_time

改动：
- BacktestOrchestrator.__init__ 增加可选 clock 参数
- harness/CLI 共享同一 VirtualClock
- _process_binding 把 self.clock 注入 feature_engine.clock

影响：
- 不需要迁移；不传 clock 时行为与之前一致
- Phase 7 测试集（324 passed）确认无回归
```

### 8.3 docs

```
docs: add commit message convention

问题：
- 缺乏统一 commit 规范，难以程序化生成 CHANGELOG

改动：
- 新增 docs/contributing/commit-convention.md
- 明确 type / scope / subject / body 写作模板
- 列出 BREAKING CHANGE 表达与示例

影响：
- 仅文档变更，无代码改动
- 后续 PR 评审可对照本规范
```

### 8.4 refactor

```
refactor(manifest): extract ManifestBuilder from BacktestRunManifest

问题：
- manifest dataclass 字段过多，构建逻辑散落各调用点
- 测试难以覆盖「字段缺失/版本不匹配」等异常路径

改动：
- 把构建逻辑搬入 ManifestBuilder（已是 Phase 1 雏形）
- 新增 to_dict / from_dict 路径使用 dataclasses.asdict
- 修复 BacktestRunManifest.from_dict 的 schema_version-based 类型分发

影响：
- 内部 API；不影响 manifest JSON 格式
- Phase 4-7 测试全部通过
```

---

## 9. 工具链（可选）

- **commitlint** + **husky** 强制约束
- **commitizen** 交互式提交
- **standard-version** 自动生成 CHANGELOG

是否引入工具链留待 Phase 决策。

---

## 10. 常见反模式

| 反模式 | 修正 |
| --- | --- |
| `update` / `stuff` | 替换为具体动词+对象 |
| `feat: WIP` | 拆分或不合并 |
| `feat+fix+refactor` | 拆分为三个提交 |
| `feat:` 之后冒号后立即大写 | 改为小写（专有名词除外） |
| subject > 72 字符 | 截断到动词 + 名词短句 |
| body 写「改了 X、Y、Z」而不说 why | 改为说明问题与决策 |

---

## 11. 评审要点

每次评审或合并 PR 时，检查：

1. type 在白名单内
2. scope 在白名单内（或省略）
3. subject ≤ 72 字符、祈使语气、无句号
4. body 解释 why 而非 what
5. BREAKING CHANGE 在 footer 或 `!` 中标注
6. Commit 信息与改动文件一致（无提交「chore: typo」却改了核心模块）

---

## 12. 与本仓库其他规范的关系

- **架构决策**：`docs/decisions/` 与 `docs/architecture/`
- **Golden Case 变更**：`docs/decisions/backtest-open-questions.md` 必须同步
- **重大重构**：必须在 `PLANS-backtest-engine.md` 维护同步

提交规范之外，技术决策仍走 Architectural Decision Record 流程。
