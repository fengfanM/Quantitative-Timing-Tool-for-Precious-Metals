# Quantitative Timing Tool for Precious Metals

面向国内黄金、白银和黄金积存类资产的量化择时 Web 工具。项目使用 **Streamlit + AKShare + vectorbt + pandas + Plotly**，提供从免费公开数据获取、因子打分、无未来函数回测、稳健参数寻优，到实时买卖决策辅助的一体化研究终端。

> 风险提示：本项目仅用于量化研究、策略复盘和教学演示，不构成任何投资建议、理财建议或收益承诺。历史回测不代表未来收益，任何真实交易都需要用户自行判断并承担风险。

## Table of Contents

- [Project Positioning](#project-positioning)
- [Industry Context](#industry-context)
- [Common Practice in Precious Metals Timing](#common-practice-in-precious-metals-timing)
- [What This Project Builds](#what-this-project-builds)
- [Technical Architecture](#technical-architecture)
- [Strategy Design](#strategy-design)
- [No-Lookahead and Backtest Discipline](#no-lookahead-and-backtest-discipline)
- [Robust Optimization](#robust-optimization)
- [Realtime Decision Workflow](#realtime-decision-workflow)
- [Quick Start](#quick-start)
- [Self Tests](#self-tests)
- [Repository Structure](#repository-structure)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License](#license)

## Project Positioning

国内普通投资者可交易的贵金属资产通常包括：

- 上海黄金交易所相关现货报价或挂钩产品
- 银行黄金积存、积存金、账户贵金属替代产品
- 黄金 ETF、白银 ETF、商品基金
- 现金、货币基金、短债基金等防守资产

很多投资者的问题不是“不知道黄金白银长期有配置价值”，而是：

- 什么时候应该进攻白银？
- 什么时候应该持有黄金？
- 什么时候应该退回黄金积存或现金？
- 如何避免凭感觉追涨杀跌？
- 如何知道一个策略是不是偷看未来、过拟合或者只在某段历史里好看？

本项目的目标是把这些问题产品化成一个可运行的 Web 工具：每天拉取公开数据，生成最新信号，给出目标仓位和买卖金额，并能复盘策略在历史区间中的风险收益表现。

## Industry Context

贵金属量化择时通常处在宏观资产配置、商品 CTA、风险平价和多因子择时的交叉区域。行业内比较成熟的思路包括：

- **趋势跟随**：黄金和白银在大级别趋势中容易出现持续行情，因此移动均线、动量、突破系统仍然是常见基线。
- **宏观驱动**：黄金受实际利率、美元指数、通胀预期、避险需求影响明显；白银还受工业需求和风险偏好影响。
- **波动率管理**：贵金属特别是白银波动大，单纯追收益容易承受深回撤，因此很多机构会用波动率分位、目标波动率或仓位上限控制风险。
- **跨资产轮动**：不是每天都必须持有进攻资产。现金、短债、货币基金和低波动黄金类产品常用于风险关闭阶段。
- **样本外验证**：机构策略研究普遍不会只看全样本最优参数，而会做训练/验证、滚动窗口、压力测试和交易成本敏感性分析。

目前前沿实践中，机器学习、另类数据和高频订单流也常被使用，但它们通常需要更高质量的数据、更严格的交易执行和更复杂的风控体系。对普通国内贵金属投资场景而言，一个透明、低依赖、可解释、可复核的日频多因子择时系统更实用，也更容易避免“黑箱优化”的幻觉。

## Common Practice in Precious Metals Timing

行业和研究中常见的贵金属择时框架大致可以分为几类。

### 1. Trend Following

使用价格相对均线、均线交叉、N 日动量或通道突破判断趋势。优点是简单、可解释、适合捕捉大行情；缺点是在震荡市容易反复打脸。

本项目使用：

- 沪金 50 日 / 200 日均线结构
- 沪金 20 日 / 60 日价格动量
- 沪金跌破 200 日均线的强制防守规则

### 2. Macro Timing

黄金通常和美元指数、实际利率、通胀预期、流动性环境相关。由于免费公开数据中实际利率和通胀预期数据不总是稳定，本项目选择更容易通过 AKShare 获取的代理变量：

- 美元指数
- 10 年期美债收益率
- 中国 CPI 同比

这些变量并不是完整宏观模型，只是用于构造可解释的宏观环境得分。

### 3. Volatility Regime Control

白银进攻性更强，历史波动显著高于黄金。很多策略失败不是因为方向判断完全错，而是因为在高波动阶段仓位过重导致回撤不可承受。

本项目使用沪金 20 日波动率分位，波动率越低，风险环境得分越高。

### 4. Defensive Asset Switching

择时策略不应该只有“买黄金”和“买白银”两个动作。风险关闭时切换到防守资产，是降低最大回撤的重要手段。

本项目提供两个防守层级：

- 黄金积存类防守资产：用 AU9999 价格替代，模拟国内黄金积存产品
- 现金类资产：用 2% 年化货币基金收益模拟

## What This Project Builds

这个项目实现了一个完整的单文件 Streamlit Web 应用，功能包括：

- 首页实时信号看板
- 实时买卖决策页
- 策略回测页
- 稳健参数寻优页
- 交易明细页
- 参数调整页
- 回测防坑审计
- 交易明细 CSV 导出
- 今日买卖清单 CSV 导出

核心文件是：

```text
precious_metals_timing_app.py
```

为了降低部署门槛，应用支持：

```bash
python3 precious_metals_timing_app.py
```

首次运行会自动检查并安装缺失依赖，然后启动 Streamlit 服务。

## Technical Architecture

项目采用单文件实现，但内部按模块化方式组织。这样既满足“零配置、易部署”，也尽量保持代码可读性。

```text
┌──────────────────────────────────────────────────────────┐
│                    Streamlit Web UI                      │
│  首页 / 实时决策 / 回测 / 寻优 / 交易明细 / 参数调整        │
└───────────────────────────────┬──────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────┐
│                  Strategy & Risk Engine                   │
│  因子打分 / 仓位映射 / 止损 / 200日均线防守 / 信号延后执行  │
└───────────────────────────────┬──────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────┐
│                    Backtest Engine                        │
│  vectorbt Portfolio / 手写净值兜底 / 指标计算 / 交易明细    │
└───────────────────────────────┬──────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────┐
│                    Data Layer                             │
│  AKShare / 超时保护 / 降级策略 / 日频对齐 / 缓存            │
└──────────────────────────────────────────────────────────┘
```

### Data Layer

数据层负责：

- 获取上金所黄金历史行情
- 获取上金所白银历史行情
- 获取上金所实时行情
- 获取美元指数、美债收益率、中国 CPI
- 对齐到上金所交易日
- 处理缺失值、字段变化和接口超时

主要 AKShare 接口：

```python
ak.spot_hist_sge(symbol="Au99.99")
ak.spot_hist_sge(symbol="Ag99.99")
ak.spot_quotations_sge(...)
ak.index_global_hist_em(symbol="美元指数")
ak.bond_zh_us_rate(...)
ak.macro_china_cpi()
```

由于免费公开接口可能出现慢响应或断连，应用把部分慢接口放入可终止子进程中调用。超时后不会让页面崩溃，而是给出页面提示并使用中性宏观因子或历史价格降级运行。

### Strategy Layer

策略层负责：

- 计算波动率、宏观、趋势、动量四类得分
- 合成 0-10 分综合得分
- 把得分映射为目标仓位
- 应用风控规则
- 把收盘信号延后到下一交易日执行

### Backtest Layer

回测层负责：

- 使用 `vectorbt.Portfolio.from_orders` 构建组合
- 计入手续费和滑点
- 输出净值、回撤、收益率、夏普、胜率、盈亏比
- 生成调仓明细
- 在 vectorbt 不可用时使用透明手写净值作为兜底

### UI Layer

UI 层使用 Streamlit 和 Plotly：

- `st.metric` 展示核心信号
- `st.dataframe` 展示行情、交易和审计表
- Plotly 展示净值曲线、回撤曲线、仓位热力图、因子曲线
- `st.download_button` 支持导出交易明细和买卖清单

## Strategy Design

### Asset Universe

| 类型 | 标的 | 实现方式 |
| --- | --- | --- |
| 进攻 | 沪金 AU9999 | AKShare 上金所 Au99.99 |
| 进攻 | 沪银 AG9999 | AKShare 上金所 Ag99.99 |
| 防守 | 工银存积金模拟 | 使用 AU9999 价格替代 |
| 防守 | 货币基金 | 2% 年化日复利模拟 |

### Factor System

四个因子都转换为 0-10 分：

| 因子 | 含义 | 得分方向 |
| --- | --- | --- |
| 波动率因子 | 沪金 20 日年化波动率分位 | 波动率越低，得分越高 |
| 宏观因子 | 美元指数、美债收益率、CPI | 美元走弱、收益率下行、CPI 较高更利多 |
| 趋势因子 | 沪金相对 50/200 日均线结构 | 趋势越强，得分越高 |
| 动量因子 | 沪金 20/60 日价格动量 | 动量越强，得分越高 |

### Position Mapping

| 综合得分 | 目标仓位 |
| --- | --- |
| `score >= 8` | 100% 沪银 |
| `6 <= score < 8` | 70% 沪金 + 30% 沪银 |
| `4 <= score < 6` | 100% 沪金 |
| `2 <= score < 4` | 100% 存积金模拟 |
| `score < 2` | 100% 货币基金 |

这个映射体现的是一个从进攻到防守的风险阶梯。白银只在高分状态下持有，因为其波动和回撤风险更高；黄金作为中等风险状态的主资产；低分状态切换到黄金积存或现金。

### Risk Controls

本项目实现两条明确风控：

- 单笔持仓亏损达到阈值后，切换至存积金防守。
- 沪金跌破 200 日均线后，强制切换至存积金防守。

风控信号同样遵守收盘后计算、下一交易日执行的规则。

## No-Lookahead and Backtest Discipline

量化回测最常见的问题不是代码跑不出来，而是结果太好看但不真实。这个项目重点处理以下陷阱。

### 1. Signal Timing

策略在 `t` 日收盘后计算信号。回测仓位使用：

```python
execution_weights = decision_weights.shift(1)
```

因此 `t` 日生成的信号只能影响 `t+1` 日执行仓位。

### 2. Macro Data Availability

CPI 是月度数据，不应该把统计月份当成当天可见数据。项目中把 CPI 延后到次月初才进入日频因子。

### 3. Transaction Cost

回测显式计入：

- 交易手续费
- 滑点
- 日度调仓换手成本

### 4. Parameter Overfitting

项目不把“全样本最优”作为默认结论。稳健寻优页采用训练/验证分离：

- 训练期用于排序参数
- 验证期用于检查泛化表现

### 5. Backtest Audit

回测页内置审计表，检查：

- 信号是否延后执行
- 仓位是否每日闭合
- CPI 是否滞后处理
- 交易记录是否按时间排序
- 参数寻优是否训练/验证隔离

## Robust Optimization

“找到最优年化收益”很容易诱导过拟合。更稳妥的做法是寻找风险调整后更稳健的参数。

项目中的寻优目标使用 Calmar 类思想：

```text
score = annual_return / abs(max_drawdown) + sharpe_bonus
```

并使用综合稳健分排序：

```text
robust_score = 0.7 * train_score + 0.3 * min(train_score, validation_score)
```

这个设计有两个目的：

- 如果训练期很好、验证期很差，综合分会被压低。
- 如果某组参数年化较高但回撤也很高，排名不会盲目靠前。

候选参数集也故意保持克制，不做大规模暴力网格搜索。原因是参数空间越大，越容易在历史噪声中找到“看起来神奇”的参数。

## Realtime Decision Workflow

实时买卖决策页用于把策略信号转换成具体操作金额。

流程如下：

1. 应用拉取最新可得行情。
2. 用最近一个可得收盘日计算因子和综合得分。
3. 输出最新目标仓位。
4. 用户输入当前沪金、沪银、存积金和现金市值。
5. 系统根据目标仓位计算目标市值。
6. 系统输出每个资产的买入、卖出或持有金额。
7. 用户在实际交易平台复核报价、产品规则和风险后自行决策。

示例：

```text
当前资产：100,000 元现金
目标仓位：100% 沪金
建议：买入 100,000 元沪金，卖出/持有其他资产
```

注意：实时页使用的是“最新可得收盘信号”。如果当天尚未收盘，信号本质上仍来自上一交易日或最近可得数据。

## Quick Start

### Zero-Config Start

```bash
python3 precious_metals_timing_app.py
```

首次运行会自动安装缺失依赖，然后启动 Streamlit。启动后访问控制台显示的本地地址，通常为：

```text
http://localhost:8501
```

### Manual Install

```bash
python3 -m pip install -r requirements.txt
streamlit run precious_metals_timing_app.py
```

### Dependencies

```text
streamlit
akshare
vectorbt
pandas
numpy
plotly
```

## Self Tests

```bash
python3 -m py_compile precious_metals_timing_app.py
python3 precious_metals_timing_app.py --self-test
python3 precious_metals_timing_app.py --data-test
```

### `--self-test`

使用本地模拟数据验证核心逻辑：

- 首日默认现金仓位
- `t` 日信号在 `t+1` 日执行
- 跌破 200 日均线后切换防守
- 回测净值不为空
- 参数寻优训练期和验证期严格分离
- 实时买卖清单能生成买入/卖出动作

### `--data-test`

使用真实 AKShare 数据跑默认数据链路和回测链路。由于免费公开接口可能限流或超时，如果宏观/实时接口失败，测试会显示 warning，但只要历史金银行情和回测链路正常，仍可通过。

## Repository Structure

```text
.
├── precious_metals_timing_app.py
├── requirements.txt
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── docs/
│   ├── DATA_SOURCES.md
│   ├── METHODOLOGY.md
│   └── RISK_DISCLOSURE.md
└── .github/
    ├── ISSUE_TEMPLATE/
    └── workflows/
```

## Operational Notes

### Data Source Stability

AKShare 是免费公开数据接口，对研究很友好，但不应被视为交易级行情服务。接口可能出现：

- 网络超时
- 字段变化
- 上游限流
- 数据延迟
- 临时不可用

应用内有超时和降级逻辑，但做真实交易前必须复核正式交易平台报价。

### Product Mapping

“工银存积金”在项目中使用 AU9999 价格作为代理。这是研究近似，不代表真实产品的买卖价差、申购赎回规则、手续费或交易时间。

### Cash Proxy

货币基金用 2% 年化日复利模拟。真实货币基金收益率会变化，也可能有确认日和赎回到账延迟。

## Known Limitations

- 单文件设计便于部署，但不如多模块工程适合大型团队协作。
- 宏观因子是简化代理，不是完整实际利率模型。
- 免费数据源不保证实时性和稳定性。
- 参数寻优使用有限候选集，目的是稳健而非穷尽最优。
- 当前策略是日频择时，不适合高频或盘中交易。
- 回测未完整模拟所有银行积存金和基金产品的申购赎回细则。

## Roadmap

可能的后续方向：

- 增加黄金 ETF、白银 ETF、商品基金等可交易替代标的
- 增加滚动 walk-forward 寻优
- 增加交易成本敏感性分析
- 增加压力测试和极端行情区间复盘
- 增加本地数据缓存文件，减少重复访问上游接口
- 增加 Docker 部署方式
- 拆分为更标准的 Python package 结构
- 增加单元测试目录和 CI 覆盖率报告

## Documentation

- [Methodology](docs/METHODOLOGY.md)
- [Data Sources](docs/DATA_SOURCES.md)
- [Risk Disclosure](docs/RISK_DISCLOSURE.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

MIT License. See [LICENSE](LICENSE).
