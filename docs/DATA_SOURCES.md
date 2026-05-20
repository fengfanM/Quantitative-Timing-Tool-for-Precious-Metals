# Data Sources

本项目使用 AKShare 免费公开接口，不需要 API key。

## Main Interfaces

- `ak.spot_hist_sge(symbol="Au99.99")`：上海黄金交易所 Au99.99 历史行情
- `ak.spot_hist_sge(symbol="Ag99.99")`：上海黄金交易所 Ag99.99 历史行情
- `ak.spot_quotations_sge(...)`：上金所实时行情
- `ak.index_global_hist_em(symbol="美元指数")`：美元指数历史行情
- `ak.bond_zh_us_rate(...)`：中美国债收益率
- `ak.macro_china_cpi()`：中国 CPI

## Fallbacks

- 如果沪银 `Ag99.99` 历史行情不可用，应用会尝试使用上海银基准价近似。
- 如果实时行情不可用，首页使用最近一个历史收盘价展示。
- 如果美元指数、美债收益率或 CPI 不可用，宏观因子使用中性值并在页面提示。

## Operational Caveats

免费公开接口不适合被视为交易级行情源。做实盘决策前，请使用券商、银行、交易所或行情服务商提供的正式报价复核。
