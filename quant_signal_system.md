# 短线量化交易建议系统方案

## 1. 系统定位

本系统的目标不是直接执行自动交易，而是构建一套：

> 实时 Alpha 信号生成器 + 延迟评价系统 + 影子回测系统

系统实时监测指定股票，根据行情和技术指标给出：

* 买入建议：Buy
* 卖出或减仓建议：Sell
* 观望建议：Hold

同时记录每一次建议产生时的市场环境，并在建议发出后的若干时间窗口内，对建议有效性进行评价。

第一阶段只验证模型和信号是否有效，不连接真实交易账户，不自动下单。

---

## 2. 总体架构

```text
实时行情
   ↓
行情标准化
   ↓
增量指标计算
   ↓
市场状态识别
   ↓
信号模型
   ↓
SignalEvent 持久化
   ├── 实时展示：Buy / Sell / Hold
   ├── 模拟持仓系统
   └── 延迟评价器
            ↓
      5分钟 / 15分钟 / 30分钟 / 60分钟 / 收盘后评价
            ↓
      模型统计、分组分析和版本比较
```

系统可以划分为以下几个模块：

| 模块                   | 主要职责                   |
| -------------------- | ---------------------- |
| Market Data          | 获取 Tick、逐笔成交、1分钟或5分钟K线 |
| Data Normalizer      | 统一时间戳、价格、成交量和交易状态      |
| Feature Engine       | 实时计算技术指标和量价特征          |
| Market Regime Engine | 判断趋势、震荡、放量、缩量等市场状态     |
| Signal Engine        | 根据规则或模型生成交易建议          |
| Signal Store         | 保存信号、指标、价格和模型版本        |
| Evaluator            | 在未来若干时间点评价信号有效性        |
| Paper Portfolio      | 模拟持仓、成交、费用和滑点          |
| Dashboard            | 展示实时建议和历史统计结果          |

对于单只股票、分钟级监测，第一版使用 Python 单进程即可，不需要一开始就引入 Kafka、Flink 等大型基础设施。

---

## 3. 信号事件设计

业界通常不会只保存一个简单的 `Buy` 或 `Sell`，而是保存完整的信号事件。

建议定义如下数据结构：

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SignalEvent:
    signal_id: str
    symbol: str

    # 时间信息
    event_time: datetime
    market_data_time: datetime
    executable_time: datetime

    # 价格信息
    reference_price: float
    executable_price: float | None

    # 信号信息
    direction: int
    score: float
    confidence: float
    horizon_seconds: int

    # 信号解释
    reason_codes: list[str]

    # 模型版本
    strategy_name: str
    strategy_version: str

    # 信号产生时的完整特征快照
    feature_snapshot: dict[str, Any]
```

其中：

| 字段                 | 含义                       |
| ------------------ | ------------------------ |
| `event_time`       | 模型生成建议的时间                |
| `market_data_time` | 模型实际使用的行情时间              |
| `executable_time`  | 理论上最早可以执行的时间             |
| `reference_price`  | 信号产生时看到的价格               |
| `executable_price` | 模拟执行时实际使用的价格             |
| `direction`        | `1` 为买入，`-1` 为卖出，`0` 为观望 |
| `score`            | 信号强度，例如 `-1.0 ~ 1.0`     |
| `confidence`       | 模型置信度，例如 `0 ~ 1`         |
| `horizon_seconds`  | 模型预计信号有效时间               |
| `reason_codes`     | 信号触发原因                   |
| `strategy_version` | 策略版本，用于区分不同模型            |

---

## 4. 时间和价格处理

短线策略中，时间处理比指标本身更重要。

例如模型在 `10:30:00` 收到一根完整的1分钟K线，则模型不能假设自己可以用这根K线的最低价成交。

建议区分三个时间：

```text
market_data_time
    模型使用的数据所属时间

event_time
    模型完成计算并发出信号的时间

executable_time
    信号在现实中最早可以执行的时间
```

模拟成交价格可以选择：

* 下一笔成交价
* 下一分钟开盘价
* 信号产生后延迟1秒、3秒或5秒的价格
* 按买一卖一价格模拟成交
* 按成交量加权价格模拟成交

不要直接使用信号K线内部的最高价、最低价或收盘前不可见的信息，否则会产生前视偏差。

---

## 5. 第一版输入数据

第一版可以只使用分钟级行情。

### 5.1 个股行情

```text
开盘价 Open
最高价 High
最低价 Low
收盘价 Close
成交量 Volume
成交额 Amount
换手率 Turnover
买卖价差 Spread
```

### 5.2 市场环境

```text
所属行业指数涨跌幅
所属概念板块涨跌幅
大盘指数涨跌幅
市场上涨家数和下跌家数
半导体、科技或相关行业指数
```

### 5.3 可选增强数据

```text
逐笔成交
Level-2 买卖盘
大单成交
主动买入和主动卖出
盘口委托变化
北向资金或行业资金流
公告和新闻事件
```

第一版不建议过早引入复杂数据。先保证基础行情、时间戳和评价体系正确。

---

## 6. 特征工程

### 6.1 收益率特征

```text
1分钟收益率
3分钟收益率
5分钟收益率
10分钟收益率
20分钟收益率
60分钟收益率
```

计算方式：

```python
return_n = current_price / price_n_minutes_ago - 1
```

### 6.2 趋势特征

```text
MA5、MA10、MA20
EMA5、EMA10、EMA20
均线斜率
均线多头或空头排列
价格距离均线的偏离程度
短周期高点和低点
```

### 6.3 成交量特征

```text
当前成交量相对过去5分钟均值
当前成交量相对过去20分钟均值
量比
成交额增速
放量上涨
放量下跌
缩量回调
缩量上涨
```

### 6.4 波动率特征

```text
过去5分钟波动率
过去20分钟波动率
真实波幅 ATR
最高价和最低价区间
波动率突然放大
```

### 6.5 日内位置特征

```text
当前价格距离日内最高点的比例
当前价格距离日内最低点的比例
当前价格在日内区间中的位置
是否突破日内新高
是否跌破日内低点
```

例如：

```python
position = (
    current_price - intraday_low
) / (
    intraday_high - intraday_low
)
```

### 6.6 相对强弱特征

```text
个股涨跌幅 - 行业涨跌幅
个股涨跌幅 - 大盘涨跌幅
个股5分钟收益 - 板块5分钟收益
个股回撤 - 板块回撤
```

相对强弱通常比单独观察个股涨跌幅更有意义。

---

## 7. 市场状态识别

同一个信号在不同市场环境下可能具有完全不同的有效性。

建议识别以下状态：

```text
趋势上涨
趋势下跌
高位震荡
低位震荡
放量突破
放量下跌
缩量回调
快速拉升
快速跳水
板块共振
个股独立上涨
个股弱于板块
```

例如：

```python
if (
    price > ma20
    and ma5 > ma10 > ma20
    and volume_ratio > 1.5
):
    regime = "TREND_UP"

elif volatility > volatility_threshold:
    regime = "HIGH_VOLATILITY"

else:
    regime = "RANGE"
```

模型统计时，应分别观察不同市场状态下的效果，而不能只看总体胜率。

---

## 8. 信号模型

第一版不建议直接使用深度学习模型。

建议先建立几个可解释的基线策略。

### 8.1 放量突破策略

示例条件：

```text
价格突破过去20分钟最高价
当前成交量大于过去20分钟平均成交量的1.5倍
个股强于所属板块
距离日内最高点较近
短周期均线向上
```

输出：

```text
方向：Buy
信号强度：0.7
建议有效期：15分钟
触发原因：放量突破、板块共振、相对强势
```

### 8.2 缩量回调策略

示例条件：

```text
中期趋势仍然向上
价格回调至MA10或MA20附近
回调期间成交量持续缩小
没有跌破关键支撑
板块未明显转弱
```

输出：

```text
方向：Buy
建议有效期：30分钟
触发原因：趋势内缩量回调
```

### 8.3 冲高回落策略

示例条件：

```text
短时间快速拉升
成交量显著放大
价格接近日内高点
高位出现长上影或连续回落
个股开始弱于板块
```

输出：

```text
方向：Sell
建议有效期：10分钟
触发原因：冲高回落、量价背离
```

### 8.4 超买超卖策略

示例条件：

```text
短周期跌幅过大
RSI进入超卖区域
价格偏离均线过远
成交量开始衰减
板块没有继续加速下跌
```

该策略更适合震荡行情，不适合强趋势下跌行情。

---

## 9. 信号输出格式

每条建议应包含：

```json
{
  "symbol": "300346.SZ",
  "time": "2026-07-03 10:30:03",
  "signal": "BUY",
  "score": 0.74,
  "confidence": 0.68,
  "reference_price": 42.35,
  "horizon_minutes": 15,
  "reasons": [
    "放量突破20分钟高点",
    "个股强于半导体板块",
    "成交量为20分钟均值的1.8倍"
  ],
  "risk": {
    "stop_reference": 41.90,
    "invalid_condition": "跌回突破位并放量"
  },
  "strategy_version": "volume_breakout_v1.2"
}
```

前端展示可以简化为：

```text
10:30:03  BUY
价格：42.35
强度：0.74
置信度：68%
有效期：15分钟

原因：
1. 放量突破20分钟高点
2. 个股明显强于板块
3. 成交量达到20分钟均值的1.8倍

失效条件：
跌回突破位并放量
```

---

## 10. 建议有效性评价

### 10.1 固定时间窗口评价

对每条信号计算：

```text
1分钟后收益
5分钟后收益
10分钟后收益
15分钟后收益
30分钟后收益
60分钟后收益
收盘收益
次日开盘收益
```

买入信号收益：

```text
future_return = future_price / executable_price - 1
```

统一方向收益：

```text
signal_return =
    direction × future_return - transaction_cost
```

其中：

```text
Buy：direction = 1
Sell：direction = -1
```

这样：

```text
signal_return > 0
```

统一表示信号方向正确。

对于A股，`Sell` 更适合解释为：

```text
减仓
清仓
停止加仓
风险规避
```

而不是默认建立空头仓位。

---

## 11. 三重障碍评价

固定时间后的价格并不能完整反映信号过程。

例如：

```text
信号发出后先上涨2%
随后回落至原点
```

如果只观察30分钟后的价格，会认为信号无效，但真实交易中可能已经触发止盈。

可以使用三重障碍法：

```text
上障碍：+1.5%
下障碍：-0.8%
时间障碍：30分钟
```

评价规则：

| 触发情况   |   标签 |
| ------ | ---: |
| 先达到止盈线 | `+1` |
| 先达到止损线 | `-1` |
| 到期均未触发 |  `0` |

伪代码：

```python
def triple_barrier_label(
    prices: list[float],
    entry_price: float,
    take_profit: float,
    stop_loss: float,
) -> int:
    for price in prices:
        ret = price / entry_price - 1

        if ret >= take_profit:
            return 1

        if ret <= -stop_loss:
            return -1

    return 0
```

对于卖出信号，需要根据方向统一转换收益。

---

## 12. MFE 和 MAE

每条信号还应记录：

### MFE

Maximum Favorable Excursion，最大有利波动。

表示信号发出后，价格沿正确方向最大移动了多少。

### MAE

Maximum Adverse Excursion，最大不利波动。

表示信号发出后，价格沿错误方向最大移动了多少。

例如：

```text
10:30 发出 Buy
执行价格：50.00

10:34 最低：49.70
MAE：-0.60%

10:38 最高：51.20
MFE：+2.40%
```

这些信息可以用于判断：

```text
止损是否设置过紧
止盈是否设置过低
信号通常需要多久生效
信号是否经常先下跌再上涨
不同市场状态下风险是否不同
```

建议记录：

```text
MFE
MAE
达到MFE的时间
达到MAE的时间
首次达到止盈的时间
首次达到止损的时间
```

---

## 13. 评价指标

不要只看胜率。

### 13.1 基础指标

| 指标                   | 含义         |
| -------------------- | ---------- |
| Signal Count         | 信号总数       |
| Signal Coverage      | 模型产生信号的频率  |
| Hit Rate             | 方向正确率      |
| Average Return       | 平均方向收益     |
| Median Return        | 中位数方向收益    |
| Average MFE          | 平均最大有利波动   |
| Average MAE          | 平均最大不利波动   |
| Profit Factor        | 总盈利除以总亏损   |
| Max Consecutive Loss | 最大连续失败次数   |
| Expected Value       | 单次信号平均期望收益 |

### 13.2 期望收益

```text
Expected Value
= 胜率 × 平均盈利
- 失败率 × 平均亏损
- 交易成本
```

例如：

```text
胜率：42%
平均盈利：2.0%
平均亏损：0.7%
```

该策略仍然可能具有正期望。

而：

```text
胜率：68%
平均盈利：0.3%
平均亏损：1.5%
```

可能是负期望策略。

### 13.3 分组统计

应按以下维度拆分模型效果：

```text
不同时间段
不同波动率环境
不同大盘状态
不同板块状态
不同成交量水平
不同信号强度
不同模型置信度
不同持有时间
不同市场趋势
```

例如：

```text
10:00以前
10:00至11:30
13:00至14:00
14:00以后
```

很多短线信号只在特定时间段有效。

---

## 14. 置信度校准

如果模型输出 `confidence = 0.8`，并不代表它真的有80%的准确率。

需要做置信度分桶：

| 置信度区间     | 信号数量 | 实际胜率 |
| --------- | ---: | ---: |
| 0.50～0.60 |  320 |  52% |
| 0.60～0.70 |  210 |  58% |
| 0.70～0.80 |  130 |  65% |
| 0.80～0.90 |   45 |  69% |
| 0.90～1.00 |   10 |  60% |

理想情况下，置信度越高，实际表现应越好。

如果高置信度信号没有明显优于低置信度信号，说明模型的置信度没有实际意义。

---

## 15. 回测系统设计

回测和实时系统应尽量共用同一套策略代码。

建议设计统一接口：

```python
class Strategy:
    def on_bar(
        self,
        bar: "Bar",
        state: "StrategyState",
    ) -> "Signal | None":
        raise NotImplementedError
```

历史回测：

```text
历史K线
   ↓
Strategy.on_bar()
   ↓
SignalEvent
   ↓
Evaluator
```

实时运行：

```text
实时K线
   ↓
Strategy.on_bar()
   ↓
SignalEvent
   ↓
Evaluator
```

两者的区别应该只在数据源：

```python
class HistoricalDataSource:
    pass


class LiveDataSource:
    pass
```

不要分别维护：

```text
backtest_signal.py
live_signal.py
```

否则两套逻辑很容易逐渐不一致。

---

## 16. 回测偏差控制

### 16.1 前视偏差

禁止使用信号产生时尚未完成的数据。

例如：

```text
使用尚未收盘的1分钟K线最终成交量
使用未来最高价或最低价
使用当天收盘后才公布的数据
```

### 16.2 数据泄漏

训练模型时，未来数据不能进入当前特征。

例如：

```text
使用全量数据计算标准化参数
先观察完整行情再定义标签
用未来成交量补全当前缺失值
```

### 16.3 幸存者偏差

如果以后扩展到多股票，需要包含：

```text
退市股票
长期停牌股票
曾经进入指数但后来被剔除的股票
```

不能只回测当前仍然存在的股票。

### 16.4 参数过拟合

不要在同一份数据上不断尝试参数，最后只展示最优结果。

例如：

```text
MA周期从3到100全部测试
止盈从0.1%到5%全部测试
止损从0.1%到5%全部测试
```

参数搜索次数越多，偶然找到“优秀策略”的概率越高。

### 16.5 成本低估

至少模拟：

```text
手续费
印花税
买卖价差
滑点
信号延迟
涨跌停无法成交
停牌无法成交
成交量不足
```

---

## 17. Walk-Forward 滚动验证

建议使用滚动训练和滚动验证。

例如：

```text
训练集：2025年1月至3月
验证集：2025年4月

训练集：2025年2月至4月
验证集：2025年5月

训练集：2025年3月至5月
验证集：2025年6月
```

每次只能使用验证日期之前的数据。

这样可以模拟真实场景：

```text
模型在当时只知道历史
然后面对未知未来
```

最终统计多个验证窗口的总体表现，而不是只选择表现最好的月份。

---

## 18. 实时影子运行

历史回测通过后，不能立即认为模型有效。

还需要进行实时影子运行：

```text
模型实时接收行情
模型实时生成建议
系统记录建议
系统不执行真实交易
未来自动评价建议
```

影子运行应至少记录：

```text
实时行情到达时间
行情源时间戳
模型计算耗时
信号生成时间
模拟执行价格
未来评价结果
```

同时比较：

```text
实时信号结果
同期历史模拟器结果
```

如果两者差异较大，可能存在：

```text
实时数据延迟
数据清洗不一致
K线边界不同
缺失数据处理不同
成交价格模拟错误
策略代码版本不一致
```

---

## 19. 模拟持仓系统

即使第一阶段只评价独立信号，也建议增加一个简单的模拟持仓系统。

原因是单条信号有效，不代表连续交易后仍然有效。

模拟系统需要处理：

```text
当前是否持仓
买入后何时允许再次买入
卖出信号是否减仓或清仓
重复信号如何处理
持仓期间相反信号如何处理
最大仓位
止盈止损
交易费用
```

示例状态机：

```text
空仓
  ↓ Buy
持仓
  ↓ Sell
空仓
```

更复杂的版本：

```text
空仓
  ↓ Buy
轻仓
  ↓ Strong Buy
重仓
  ↓ Sell
轻仓
  ↓ Strong Sell
空仓
```

第一版建议只使用：

```text
0%仓位
100%仓位
```

避免过早引入复杂仓位管理。

---

## 20. 数据库设计

第一版至少需要三张表。

### 20.1 market_bars

```sql
CREATE TABLE market_bars (
    symbol VARCHAR(32) NOT NULL,
    bar_time TIMESTAMP NOT NULL,

    open_price DOUBLE PRECISION NOT NULL,
    high_price DOUBLE PRECISION NOT NULL,
    low_price DOUBLE PRECISION NOT NULL,
    close_price DOUBLE PRECISION NOT NULL,

    volume DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    turnover DOUBLE PRECISION,

    PRIMARY KEY (symbol, bar_time)
);
```

### 20.2 signal_events

```sql
CREATE TABLE signal_events (
    signal_id VARCHAR(64) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,

    event_time TIMESTAMP NOT NULL,
    market_data_time TIMESTAMP NOT NULL,
    executable_time TIMESTAMP,

    reference_price DOUBLE PRECISION NOT NULL,
    executable_price DOUBLE PRECISION,

    direction INTEGER NOT NULL,
    score DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    horizon_seconds INTEGER,

    reason_codes JSON,
    feature_snapshot JSON,

    strategy_name VARCHAR(128) NOT NULL,
    strategy_version VARCHAR(64) NOT NULL
);
```

### 20.3 signal_evaluations

```sql
CREATE TABLE signal_evaluations (
    signal_id VARCHAR(64) NOT NULL,
    evaluation_horizon_seconds INTEGER NOT NULL,

    evaluation_time TIMESTAMP NOT NULL,
    evaluation_price DOUBLE PRECISION NOT NULL,

    raw_return DOUBLE PRECISION,
    direction_return DOUBLE PRECISION,
    net_return DOUBLE PRECISION,

    mfe DOUBLE PRECISION,
    mae DOUBLE PRECISION,

    triple_barrier_label INTEGER,

    PRIMARY KEY (
        signal_id,
        evaluation_horizon_seconds
    )
);
```

---

## 21. 数据不可变原则

`signal_events` 应采用只追加、不修改的设计。

即使后续发现模型存在问题，也不能修改历史信号。

正确方式是发布新版本：

```text
volume_breakout_v1.0
volume_breakout_v1.1
volume_breakout_v2.0
```

每次信号都必须保存：

```text
策略名称
策略版本
特征版本
代码提交版本
参数配置
```

可以进一步记录：

```text
Git Commit ID
配置文件 Hash
模型文件 Hash
数据源版本
```

这样才能复现历史结果。

---

## 22. 延迟评价器

延迟评价器负责在信号产生后的指定时间点进行评价。

例如：

```text
信号时间：10:30

评价任务：
10:35 评价5分钟收益
10:45 评价15分钟收益
11:00 评价30分钟收益
11:30 评价60分钟收益
15:00 评价收盘收益
```

实现方式有两种。

### 22.1 定时任务方式

每次产生信号后，注册多个延迟任务。

适合信号数量较少的第一版系统。

### 22.2 扫描方式

Evaluator 周期性查询：

```text
哪些信号已经到达评价时间
但尚未生成评价结果
```

伪代码：

```python
def evaluate_pending_signals(now):
    pending_signals = repository.find_pending(now)

    for signal in pending_signals:
        for horizon in signal.pending_horizons:
            result = evaluator.evaluate(signal, horizon)
            repository.save_evaluation(result)
```

扫描方式更容易恢复，也更适合系统重启。

---

## 23. 技术选型

### 23.1 快速研究版

```text
Python
Pandas 或 Polars
NumPy
TA-Lib 或自行实现指标
VectorBT
SQLite
Streamlit
```

适合：

```text
快速验证指标组合
批量测试参数
观察历史信号分布
生成研究报告
```

### 23.2 实时事件驱动版

```text
行情 WebSocket
        ↓
Python asyncio
        ↓
Feature Engine
        ↓
Signal Engine
        ↓
PostgreSQL / TimescaleDB
        ↓
Evaluator Worker
        ↓
FastAPI
        ↓
Web Dashboard
```

第一版可以使用以下目录结构：

```text
quant_signal_system/
├── config/
│   └── strategy.yaml
├── data/
│   ├── data_source.py
│   ├── historical_source.py
│   └── live_source.py
├── features/
│   ├── indicators.py
│   └── feature_engine.py
├── strategies/
│   ├── base.py
│   ├── volume_breakout.py
│   └── mean_reversion.py
├── signals/
│   ├── models.py
│   └── signal_engine.py
├── evaluation/
│   ├── evaluator.py
│   ├── triple_barrier.py
│   └── metrics.py
├── portfolio/
│   └── paper_portfolio.py
├── storage/
│   ├── repository.py
│   └── database.py
├── api/
│   └── app.py
├── dashboard/
│   └── dashboard.py
├── backtest.py
└── live.py
```

---

## 24. 最小可行版本

第一版建议只做：

```text
一只股票
1分钟K线
3个基础策略
5种评价周期
SQLite数据库
简单网页展示
```

### 输入

```text
OHLCV
成交额
换手率
指数涨跌幅
板块涨跌幅
```

### 特征

```text
5分钟、10分钟、20分钟收益
MA5、MA10、MA20
均线斜率
成交量比率
短周期波动率
相对板块强弱
日内高低点位置
```

### 输出

```text
Buy / Sell / Hold
Signal Score
Confidence
预计有效时间
触发原因
失效条件
```

### 评价

```text
5分钟收益
15分钟收益
30分钟收益
60分钟收益
MFE
MAE
三重障碍标签
扣除成本后的净收益
```

---

## 25. 推荐实施阶段

### 阶段一：数据和评价系统

目标：

```text
获取稳定行情
正确生成分钟K线
保存完整市场快照
建立延迟评价器
计算MFE和MAE
```

这一阶段可以暂时不追求策略有效。

### 阶段二：规则策略基线

实现：

```text
均线突破
放量突破
缩量回调
超买超卖
冲高回落
```

目标是验证完整链路。

### 阶段三：历史回测

加入：

```text
手续费
印花税
滑点
信号延迟
涨跌停限制
停牌处理
```

使用样本外测试和 Walk-Forward 验证。

### 阶段四：实时影子运行

连续运行模型，记录：

```text
实时信号
模拟成交
未来收益
实时和回测差异
```

### 阶段五：机器学习模型

基础系统稳定后，可以尝试：

```text
Logistic Regression
Random Forest
XGBoost
LightGBM
简单神经网络
时序模型
```

模型预测目标可以是：

```text
未来15分钟是否上涨
未来30分钟方向收益
三重障碍标签
未来最大有利波动
未来风险收益比
```

---

## 26. 是否需要机器学习

第一版不建议直接使用机器学习。

原因是规则模型更容易发现系统问题：

```text
指标是否计算错误
行情时间是否错位
K线是否存在前视
信号是否重复产生
成交价格是否合理
实时和回测是否一致
评价任务是否遗漏
```

如果一开始使用复杂模型，即使结果异常，也很难判断是：

```text
模型问题
数据问题
特征问题
评价问题
执行模拟问题
```

推荐顺序：

```text
简单规则
   ↓
线性模型
   ↓
树模型
   ↓
复杂时序模型
```

---

## 27. 核心原则

该系统首先要解决的，不是如何预测涨跌，而是如何构建一套不会自欺欺人的实验体系。

核心原则如下：

1. 信号必须在产生时立即保存。
2. 历史信号不能被后续模型覆盖。
3. 实时系统和回测系统尽量共用代码。
4. 评价价格必须是现实中可执行的价格。
5. 所有模型必须记录版本。
6. 不能只展示表现最好的时间段。
7. 必须统计失败信号和连续亏损。
8. 必须加入手续费、滑点和延迟。
9. 必须使用样本外数据评价。
10. 必须先进行实时影子运行，再考虑真实交易。

---

## 28. 最终建议

第一版系统的重点不应放在复杂模型，而应放在以下四件事上：

```text
实时记录
公平评价
结果复现
防止前视
```

一个合理的第一版目标是：

> 系统能够稳定监测一只股票，根据简单规则实时生成 Buy、Sell 或 Hold 建议，完整记录信号产生时的市场环境，并自动统计信号在5分钟、15分钟、30分钟和60分钟后的有效性。

当这套链路能够长期稳定运行，并且历史回测、实时影子运行和模拟交易结果基本一致后，再逐步增加：

```text
更多股票
更多行情特征
机器学习模型
组合管理
风险控制
自动执行
```

量化系统真正困难的部分，通常不是计算均线或 RSI，而是避免：

```text
前视偏差
数据泄漏
参数过拟合
选择性展示
成本低估
回测与实时不一致
```

因此，第一阶段最重要的产物不是一个“准确率很高的模型”，而是一套可信、可复现、可持续评价的信号实验平台。
