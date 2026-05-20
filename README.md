# Quantitative Timing Tool for Precious Metals

国内贵金属量化择时策略 Web 工具。项目使用 Streamlit + AKShare + vectorbt + pandas + Plotly，面向国内黄金、白银、黄金积存类产品和现金类资产的日度择时研究。

> 风险提示：本项目仅用于量化研究、策略复盘和教学演示，不构成任何投资建议。历史回测不代表未来收益，任何实盘决策都需要用户自行承担风险。

## Features

- 单文件核心应用：`precious_metals_timing_app.py`
- 零配置启动：首次运行会自动安装缺失依赖
- 国内贵金属数据：通过 AKShare 免费公开接口获取上金所黄金/白银行情
- 严格无未来函数：收盘信号延后到下一交易日执行
- 风控规则：单笔止损、跌破 200 日均线转防守
- 策略回测：vectorbt 组合回测，含手续费和滑点
- 回测审计：展示信号延后、仓位闭合、CPI 滞后等防坑检查
- 稳健寻优：训练期选择参数、验证期验收，降低过拟合风险
- 实时决策：输入当前持仓市值，输出建议买入/卖出金额
- 交互图表：净值曲线、回撤曲线、仓位热力图、因子趋势

## Quick Start

```bash
python3 precious_metals_timing_app.py
```

启动后访问控制台显示的本地地址，通常为：

```text
http://localhost:8501
```

也可以手动安装依赖后启动：

```bash
python3 -m pip install -r requirements.txt
streamlit run precious_metals_timing_app.py
```

## Self Test

```bash
python3 precious_metals_timing_app.py --self-test
python3 precious_metals_timing_app.py --data-test
```

- `--self-test` 使用本地模拟数据验证核心逻辑，包括信号次日执行、风控切换、寻优训练/验证隔离、买卖清单生成。
- `--data-test` 使用真实 AKShare 数据跑默认数据链路和回测链路。

## Strategy Overview

资产池：

- 进攻资产：沪金 AU9999、沪银 AG9999
- 防守资产：工银存积金模拟资产（使用 AU9999 替代）、货币基金（2% 年化模拟）

因子体系：

- 波动率因子：沪金 20 日波动率分位，波动率越低得分越高
- 宏观因子：美元指数、10 年期美债收益率、中国 CPI 同比
- 趋势因子：沪金 50 日/200 日均线结构
- 动量因子：沪金 20 日/60 日价格动量

仓位映射：

- 得分 >= 8：100% 沪银
- 6 <= 得分 < 8：70% 沪金 + 30% 沪银
- 4 <= 得分 < 6：100% 沪金
- 2 <= 得分 < 4：100% 存积金替代资产
- 得分 < 2：100% 货币基金

## Backtesting Discipline

本项目重点避免常见回测陷阱：

- 因子只使用当日及以前数据
- 信号在当日收盘后产生，仓位通过 `shift(1)` 延后到下一交易日执行
- CPI 月度数据延后到次月初进入日频因子
- 参数寻优采用训练期和验证期分离
- 回测显式计入手续费和滑点
- 页面展示回测防坑审计表，便于复核关键假设

更多细节见 [docs/METHODOLOGY.md](docs/METHODOLOGY.md)。

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

## Data Source Notes

AKShare 免费公开接口可能因为网络、源站限流、字段变更而失败。应用内已经对实时行情、外盘宏观等慢接口增加超时保护；接口失败时会显示友好提示，并尽量使用中性宏观因子或历史价格降级运行。

## License

MIT License. See [LICENSE](LICENSE).
