# 本地开发环境

## 1. 结论

已确定：当前项目采用 `requirements.txt` 和本地虚拟环境管理 Python 依赖。`pyproject.toml` 仅保留项目元数据、`pytest` 和 `ruff` 的工具配置，不再作为依赖声明来源。

已确定：默认环境用于核心契约、回放、评价、Dashboard API 和测试验证；真实 AKShare 行情拉取属于可选能力，必须通过 `requirements-akshare.txt` 显式安装。

已确定：本项目仍只产生研究性 `Buy`、`Sell`、`Hold` 信号和影子评价，不连接真实券商账户，不自动执行真实交易。

## 2. 环境创建

```powershell
.\scripts\setup_venv.ps1
```

如需真实拉取 AKShare 行情：

```powershell
.\scripts\setup_venv.ps1 -WithAkshare
```

手动方式等价于：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

建议方案：需要真实行情拉取时再执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-akshare.txt
```

## 3. 常用命令

```powershell
.\scripts\test.ps1
.\scripts\test.ps1 contract
.\scripts\test.ps1 replay-golden
.\scripts\test.ps1 evaluation-recovery
```

Dashboard 本地启动：

```powershell
.\.venv\Scripts\python.exe -m quant_signal_system.dashboard --market-db reports/dashboard/market.db --signal-db reports/dashboard/signals.db --host 127.0.0.1 --port 8000
```

建议方案：若未激活虚拟环境，优先使用 `scripts/test.ps1`；该脚本会自动选择 `.venv\Scripts\python.exe`，不存在时回退到系统 `python`。

## 4. 依赖边界

- 已确定：`requirements.txt` 管理默认开发、测试和质量检查依赖，并在 Windows 环境安装 `tzdata` 以支持 `ZoneInfo("Asia/Shanghai")`。
- 建议方案：`requirements-akshare.txt` 管理真实 AKShare 数据拉取依赖，避免核心测试强依赖行情供应商 SDK。
- 已确定：所有供应商数据必须先标准化为内部 `MarketBar` / `MarketTick`，不得让策略、特征或评价核心直接依赖供应商 SDK。
- 已确定：依赖治理变更不改变信号研究、模拟成交和真实交易的系统边界。

## 5. 开放问题

- 待决策：未来是否需要按生产、开发、数据供应商进一步拆分更多 requirements 文件。
- 待决策：是否引入锁定文件或内部镜像源，用于团队协作环境中的完全可复现安装。
