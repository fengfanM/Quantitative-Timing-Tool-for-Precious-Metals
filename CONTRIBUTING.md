# Contributing

感谢关注本项目。这个项目涉及金融研究和投资决策辅助，因此贡献需要优先保证可复核性、稳定性和风险披露。

## Development Principles

- 不引入未来函数。
- 不把训练期最优包装成未来收益承诺。
- 数据源失败时必须友好降级，不能让页面直接崩溃。
- 所有策略改动必须说明经济含义。
- 所有新增参数都应有合理默认值。

## Local Checks

```bash
python3 -m py_compile precious_metals_timing_app.py
python3 precious_metals_timing_app.py --self-test
python3 precious_metals_timing_app.py --data-test
```

`--data-test` 依赖网络和 AKShare 上游接口，如果上游限流或不可用，请在 PR 中说明复现时间、错误信息和是否影响核心离线自检。

## Pull Request Checklist

- [ ] 已运行语法检查。
- [ ] 已运行 `--self-test`。
- [ ] 如果改动数据接口，已运行或说明 `--data-test` 结果。
- [ ] 如果改动策略逻辑，已说明是否影响无未来函数假设。
- [ ] 如果改动回测指标，已说明指标定义。
- [ ] 如果新增依赖，已更新 `requirements.txt`。

## Financial Content Rules

请避免使用“保证收益”“稳赚”“必胜”“实盘无风险”等表述。策略输出应被描述为研究信号或辅助决策，而不是投资建议。
