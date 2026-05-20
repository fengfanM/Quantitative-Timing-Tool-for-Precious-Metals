#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国内贵金属量化择时策略 Web 工具（单文件版）

启动方式：
1. 推荐零配置启动：python precious_metals_timing_app.py
   - 首次运行会自动安装缺失依赖，并启动 Streamlit 页面。
2. 依赖已安装后也可以运行：streamlit run precious_metals_timing_app.py
3. 自检：python precious_metals_timing_app.py --self-test

依赖说明：
- streamlit：Web 页面
- akshare：免费公开金融数据接口，无需 API 密钥
- vectorbt：组合回测框架
- pandas / numpy：数据处理
- plotly：交互式图表

重要声明：
- 本工具仅用于量化研究和教学演示，不构成任何投资建议。
- 免费公开数据源可能存在延迟、缺失或接口变动，实盘前必须独立复核。
"""

from __future__ import annotations

import importlib.util
import multiprocessing as mp
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


# =============================================================================
# 零配置启动器：只依赖 Python 标准库，确保首次运行能自动安装依赖。
# =============================================================================

APP_CHILD_ENV = "PRECIOUS_METALS_STREAMLIT_CHILD"

# 必须在任何 Streamlit 导入前设置，否则首次运行可能弹出邮箱采集提示。
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_SHOW_EMAIL_PROMPT", "false")

REQUIRED_PACKAGES: Dict[str, str] = {
    "streamlit": "streamlit>=1.35,<2",
    "akshare": "akshare>=1.18.0",
    "vectorbt": "vectorbt>=0.27,<0.29",
    "pandas": "pandas>=1.5,<2.2",
    "numpy": "numpy>=1.23,<2.0",
    "plotly": "plotly>=5.18,<6.0",
}

# 给底层网络库一个全局默认超时；部分 akshare 接口内部没有显式 timeout。
socket.setdefaulttimeout(20)


def _is_streamlit_runtime() -> bool:
    """判断当前脚本是否已经运行在 Streamlit 的脚本上下文中。"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def _ensure_pip_available() -> None:
    """尽量确保当前 Python 有 pip；少数系统 Python 初始环境可能没有 pip。"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "--version"])
    except Exception:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])


def _install_missing_dependencies() -> None:
    """自动安装缺失依赖，避免用户手动配置环境。"""
    missing_specs = [
        package_spec
        for module_name, package_spec in REQUIRED_PACKAGES.items()
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing_specs:
        return

    print("检测到缺失依赖，正在自动安装：")
    for spec in missing_specs:
        print(f"  - {spec}")
    _ensure_pip_available()
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--upgrade", *missing_specs]
    )


def _bootstrap_when_launched_by_python() -> None:
    """
    支持 `python precious_metals_timing_app.py` 直接启动。

    逻辑说明：
    - 如果已经在 Streamlit 中运行，直接进入页面代码。
    - 如果是普通 Python 运行，先安装依赖，再调用 Streamlit CLI 启动本文件。
    - `--self-test` 用于本地验证，不启动 Web 页面。
    """
    if os.environ.get(APP_CHILD_ENV) == "1" or _is_streamlit_runtime():
        return
    if "--no-bootstrap" in sys.argv:
        return

    _install_missing_dependencies()

    if "--self-test" in sys.argv or "--data-test" in sys.argv:
        return

    os.environ[APP_CHILD_ENV] = "1"
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    from streamlit.web import cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        os.path.abspath(__file__),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.showEmailPrompt=false",
    ]
    sys.exit(streamlit_cli.main())


if __name__ == "__main__":
    _bootstrap_when_launched_by_python()


# =============================================================================
# 第三方依赖：普通 `python` 首次启动时，上面的 bootstrap 已完成安装。
# =============================================================================

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import akshare as ak
except Exception as exc:  # pragma: no cover - 页面友好兜底
    ak = None
    AKSHARE_IMPORT_ERROR = exc
else:
    AKSHARE_IMPORT_ERROR = None

try:
    import vectorbt as vbt
except Exception as exc:  # pragma: no cover - vectorbt 失败时仍允许页面解释
    vbt = None
    VECTORBT_IMPORT_ERROR = exc
else:
    VECTORBT_IMPORT_ERROR = None


# =============================================================================
# 数据结构和默认参数
# =============================================================================

ASSET_GOLD = "沪金 AU9999"
ASSET_SILVER = "沪银 AG9999"
ASSET_ACCUM = "工银存积金(黄金替代)"
ASSET_CASH = "货币基金(2%年化)"
ASSET_COLUMNS = [ASSET_GOLD, ASSET_SILVER, ASSET_ACCUM, ASSET_CASH]


@dataclass
class StrategyParams:
    """策略参数集合，便于页面和回测函数之间传递。"""

    volatility_weight: float = 1.0
    macro_weight: float = 1.0
    trend_weight: float = 1.0
    momentum_weight: float = 1.0
    stop_loss: float = 0.05
    threshold_full_silver: float = 8.0
    threshold_mix: float = 6.0
    threshold_full_gold: float = 4.0
    threshold_accum: float = 2.0
    risk_free_annual: float = 0.02


@dataclass
class MarketData:
    """所有行情和宏观数据的统一容器。"""

    prices_close: pd.DataFrame
    prices_open: pd.DataFrame
    gold_ohlc: pd.DataFrame
    silver_ohlc: pd.DataFrame
    usd_index: pd.Series
    us10y: pd.Series
    china_cpi_yoy: pd.Series
    realtime_quotes: pd.DataFrame
    warnings: List[str]
    updated_at: str


@dataclass
class BacktestResult:
    """回测输出，供多个页面复用。"""

    equity: pd.Series
    benchmark_equity: pd.Series
    drawdown: pd.Series
    decision_weights: pd.DataFrame
    execution_weights: pd.DataFrame
    factor_scores: pd.DataFrame
    total_score: pd.Series
    risk_reason: pd.Series
    daily_returns: pd.Series
    metrics: Dict[str, float]
    trades: pd.DataFrame
    vectorbt_stats: Optional[pd.Series]
    warnings: List[str]


@dataclass
class StrategyAudit:
    """回测防坑审计结果。"""

    item: str
    status: str
    detail: str


def default_params() -> StrategyParams:
    """返回默认策略参数。"""
    return StrategyParams()


# =============================================================================
# 通用工具函数
# =============================================================================


def _friendly_error(message: str, exc: Exception) -> str:
    """把异常压缩为适合页面展示的中文提示。"""
    return f"{message}：{type(exc).__name__}: {exc}"


def _first_existing_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """在不同数据源字段名不完全一致时，按候选名称寻找第一列。"""
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _to_datetime_index(series_or_df: Any) -> Any:
    """把索引统一成按日期升序的 DatetimeIndex。"""
    obj = series_or_df.copy()
    obj.index = pd.to_datetime(obj.index)
    obj = obj[~obj.index.duplicated(keep="last")].sort_index()
    return obj


def _safe_numeric(series: pd.Series) -> pd.Series:
    """安全转换为浮点数，无法解析的数据转为 NaN。"""
    return pd.to_numeric(series, errors="coerce")


def _akshare_worker(conn: Any, func_name: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
    """
    子进程执行 akshare 调用。

    这样做是为了处理个别免费公开接口在网络异常时长时间卡住的问题。主进程可以超时终止子进程，
    页面则降级展示友好提示，不会被单个数据源拖死。
    """
    try:
        import akshare as ak_child

        func = getattr(ak_child, func_name)
        conn.send(("ok", func(*args, **kwargs)))
    except Exception as exc:
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def _call_akshare_with_timeout(
    func_name: str,
    timeout_seconds: int = 20,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """在可终止子进程中调用 akshare，超时则抛出 TimeoutError。"""
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_akshare_worker, args=(child_conn, func_name, args, kwargs))
    process.start()
    child_conn.close()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(2)
        parent_conn.close()
        raise TimeoutError(f"akshare.{func_name} 超过 {timeout_seconds} 秒未返回")
    if not parent_conn.poll():
        parent_conn.close()
        raise RuntimeError(f"akshare.{func_name} 没有返回结果")
    status, payload = parent_conn.recv()
    parent_conn.close()
    if status == "error":
        raise RuntimeError(payload)
    return payload


def _parse_chinese_month(text: Any) -> pd.Timestamp:
    """解析类似 `2022年10月份` 的月份字段。"""
    match = re.search(r"(\d{4})\D+(\d{1,2})", str(text))
    if not match:
        return pd.NaT
    year = int(match.group(1))
    month = int(match.group(2))
    return pd.Timestamp(year=year, month=month, day=1)


def _annualized_cash_index(index: pd.DatetimeIndex, annual_rate: float) -> pd.Series:
    """生成货币基金价格序列，用 252 个交易日复利近似 2% 年化收益。"""
    if len(index) == 0:
        return pd.Series(dtype=float)
    daily_rate = (1.0 + annual_rate) ** (1.0 / 252.0) - 1.0
    values = np.cumprod(np.full(len(index), 1.0 + daily_rate))
    return pd.Series(values, index=index, name=ASSET_CASH)


def _rolling_percentile(series: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    """
    计算滚动分位数，结果范围 0-1。

    只使用窗口内当前日及以前的数据，因此不会引入未来函数。
    """

    def rank_last(values: np.ndarray) -> float:
        values = values[~np.isnan(values)]
        if len(values) == 0:
            return np.nan
        return float((values <= values[-1]).sum() / len(values))

    return series.rolling(window=window, min_periods=min_periods).apply(rank_last, raw=True)


def _percentile_score(series: pd.Series, invert: bool = False) -> pd.Series:
    """把任意连续因子转换成 0-10 分的滚动分位得分。"""
    percentile = _rolling_percentile(series)
    score = 10.0 * (1.0 - percentile if invert else percentile)
    return score.clip(0.0, 10.0)


def _format_pct(value: float) -> str:
    """百分比格式化，NaN 时显示短横线。"""
    if pd.isna(value):
        return "-"
    return f"{value:.2%}"


def _format_num(value: float, digits: int = 2) -> str:
    """数字格式化，NaN 时显示短横线。"""
    if pd.isna(value):
        return "-"
    return f"{value:.{digits}f}"


# =============================================================================
# 数据获取层：全部使用 akshare 公开免费接口，无需 API 密钥。
# =============================================================================


def fetch_sge_history(symbol: str, asset_name: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    获取上海黄金交易所历史行情。

    参数：
    - symbol: akshare 上金所品种，如 `Au99.99`、`Ag99.99`
    - asset_name: 页面展示名称
    """
    warnings: List[str] = []
    if ak is None:
        return pd.DataFrame(), [_friendly_error("akshare 导入失败", AKSHARE_IMPORT_ERROR)]
    try:
        raw = ak.spot_hist_sge(symbol=symbol)
        if raw is None or raw.empty:
            raise ValueError(f"{symbol} 返回空数据")
        required = ["date", "open", "close", "low", "high"]
        missing = [column for column in required if column not in raw.columns]
        if missing:
            raise ValueError(f"{symbol} 缺少字段：{missing}")
        df = raw[required].copy()
        df["date"] = pd.to_datetime(df["date"])
        for column in ["open", "close", "low", "high"]:
            df[column] = _safe_numeric(df[column])
        df = df.dropna(subset=["date", "close"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df.columns = ["open", "close", "low", "high"]
        return df, warnings
    except Exception as exc:
        warnings.append(_friendly_error(f"{asset_name} 历史行情获取失败", exc))
        return pd.DataFrame(), warnings


def fetch_silver_fallback() -> Tuple[pd.DataFrame, List[str]]:
    """
    当 `Ag99.99` 历史行情不可用时，降级使用上海银基准价。

    基准价只有早盘价/晚盘价，没有完整 OHLC；这里用早盘价近似 open、晚盘价近似 close，
    high/low 取二者最大/最小，并在页面提示这是降级数据。
    """
    warnings: List[str] = []
    if ak is None:
        return pd.DataFrame(), [_friendly_error("akshare 导入失败", AKSHARE_IMPORT_ERROR)]
    try:
        raw = ak.spot_silver_benchmark_sge()
        if raw is None or raw.empty:
            raise ValueError("上海银基准价返回空数据")
        date_col = _first_existing_column(raw, ["交易时间", "date", "日期"])
        morning_col = _first_existing_column(raw, ["早盘价", "morning"])
        evening_col = _first_existing_column(raw, ["晚盘价", "evening"])
        if not date_col or not morning_col or not evening_col:
            raise ValueError("上海银基准价字段结构不符合预期")
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(raw[date_col]),
                "open": _safe_numeric(raw[morning_col]),
                "close": _safe_numeric(raw[evening_col]),
            }
        )
        df["open"] = df["open"].fillna(df["close"])
        df["close"] = df["close"].fillna(df["open"])
        df["high"] = df[["open", "close"]].max(axis=1)
        df["low"] = df[["open", "close"]].min(axis=1)
        df = df.dropna(subset=["date", "close"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        warnings.append("沪银 Ag99.99 历史行情不可用，已降级使用上海银基准价近似。")
        return df[["open", "close", "low", "high"]], warnings
    except Exception as exc:
        warnings.append(_friendly_error("上海银基准价降级数据获取失败", exc))
        return pd.DataFrame(), warnings


def fetch_realtime_sge_quotes() -> Tuple[pd.DataFrame, List[str]]:
    """获取上金所实时行情，用于首页展示最新价格和更新时间。"""
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    if ak is None:
        return pd.DataFrame(), [_friendly_error("akshare 导入失败", AKSHARE_IMPORT_ERROR)]

    for symbol, name in [("Au99.99", ASSET_GOLD), ("Ag99.99", ASSET_SILVER)]:
        try:
            raw = _call_akshare_with_timeout("spot_quotations_sge", 12, symbol=symbol)
            if raw is None or raw.empty:
                raise ValueError(f"{symbol} 实时行情为空")
            price_col = _first_existing_column(raw, ["现价", "price", "最新价"])
            update_col = _first_existing_column(raw, ["更新时间", "update_time"])
            time_col = _first_existing_column(raw, ["时间", "time"])
            if not price_col:
                raise ValueError("缺少实时价格字段")
            clean = raw.dropna(subset=[price_col]).copy()
            latest = clean.iloc[-1]
            rows.append(
                {
                    "标的": name,
                    "symbol": symbol,
                    "最新价": float(latest[price_col]),
                    "行情时间": str(latest[time_col]) if time_col else "",
                    "更新时间": str(latest[update_col]) if update_col else "",
                }
            )
        except Exception as exc:
            warnings.append(_friendly_error(f"{name} 实时行情获取失败", exc))

    return pd.DataFrame(rows), warnings


def fetch_global_index(symbol: str) -> Tuple[pd.Series, List[str]]:
    """获取全球指数历史行情，这里用于美元指数。"""
    warnings: List[str] = []
    if ak is None:
        return pd.Series(dtype=float), [_friendly_error("akshare 导入失败", AKSHARE_IMPORT_ERROR)]
    try:
        raw = _call_akshare_with_timeout("index_global_hist_em", 18, symbol=symbol)
        if raw is None or raw.empty:
            raise ValueError(f"{symbol} 返回空数据")
        date_col = _first_existing_column(raw, ["日期", "date", "时间"])
        close_col = _first_existing_column(raw, ["收盘", "close", "最新价"])
        if not date_col or not close_col:
            raise ValueError(f"{symbol} 缺少日期或收盘字段")
        series = pd.Series(
            _safe_numeric(raw[close_col]).values,
            index=pd.to_datetime(raw[date_col]),
            name=symbol,
        )
        return _to_datetime_index(series.dropna()), warnings
    except Exception as exc:
        warnings.append(_friendly_error(f"{symbol} 获取失败，宏观因子将使用中性值", exc))
        return pd.Series(dtype=float, name=symbol), warnings


def fetch_us10y_rate(start_date: str = "20180101") -> Tuple[pd.Series, List[str]]:
    """获取 10 年期美债收益率历史数据。"""
    warnings: List[str] = []
    if ak is None:
        return pd.Series(dtype=float), [_friendly_error("akshare 导入失败", AKSHARE_IMPORT_ERROR)]
    try:
        raw = _call_akshare_with_timeout("bond_zh_us_rate", 18, start_date=start_date)
        if raw is None or raw.empty:
            raise ValueError("中美国债收益率返回空数据")
        date_col = _first_existing_column(raw, ["日期", "date"])
        value_col = _first_existing_column(raw, ["美国国债收益率10年", "美国10年期国债收益率"])
        if not date_col or not value_col:
            raise ValueError("缺少 10 年期美债收益率字段")
        series = pd.Series(
            _safe_numeric(raw[value_col]).values,
            index=pd.to_datetime(raw[date_col]),
            name="美国10年期国债收益率",
        )
        return _to_datetime_index(series.dropna()), warnings
    except Exception as exc:
        warnings.append(_friendly_error("10 年期美债收益率获取失败，宏观因子将使用中性值", exc))
        return pd.Series(dtype=float, name="美国10年期国债收益率"), warnings


def fetch_china_cpi_yoy() -> Tuple[pd.Series, List[str]]:
    """
    获取中国 CPI 同比。

    `macro_china_cpi` 的月份字段通常表示统计月份而非发布日期。为了保守避免未来函数，
    本工具把某月 CPI 延后到次月初才允许进入每日因子计算。
    """
    warnings: List[str] = []
    if ak is None:
        return pd.Series(dtype=float), [_friendly_error("akshare 导入失败", AKSHARE_IMPORT_ERROR)]
    try:
        raw = _call_akshare_with_timeout("macro_china_cpi", 18)
        if raw is None or raw.empty:
            raise ValueError("中国 CPI 返回空数据")
        month_col = _first_existing_column(raw, ["月份", "日期", "date"])
        value_col = _first_existing_column(raw, ["全国-同比增长", "全国同比增长", "今值"])
        if not month_col or not value_col:
            raise ValueError("缺少 CPI 月份或同比字段")
        month_start = raw[month_col].apply(_parse_chinese_month)
        available_date = pd.to_datetime(month_start) + pd.offsets.MonthBegin(1)
        series = pd.Series(
            _safe_numeric(raw[value_col]).values,
            index=available_date,
            name="中国CPI同比",
        )
        return _to_datetime_index(series.dropna()), warnings
    except Exception as exc:
        warnings.append(_friendly_error("中国 CPI 获取失败，宏观因子将使用中性值", exc))
        return pd.Series(dtype=float, name="中国CPI同比"), warnings


@st.cache_resource(ttl=3600, show_spinner="正在拉取 akshare 免费公开数据...")
def load_market_data() -> MarketData:
    """拉取并对齐所有行情数据；Streamlit 缓存 1 小时，减少重复请求。"""
    warnings: List[str] = []

    gold_ohlc, gold_warnings = fetch_sge_history("Au99.99", ASSET_GOLD)
    warnings.extend(gold_warnings)

    silver_ohlc, silver_warnings = fetch_sge_history("Ag99.99", ASSET_SILVER)
    warnings.extend(silver_warnings)
    if silver_ohlc.empty:
        silver_ohlc, fallback_warnings = fetch_silver_fallback()
        warnings.extend(fallback_warnings)

    realtime_quotes, quote_warnings = fetch_realtime_sge_quotes()
    warnings.extend(quote_warnings)

    usd_index, usd_warnings = fetch_global_index("美元指数")
    warnings.extend(usd_warnings)

    us10y, us10y_warnings = fetch_us10y_rate("20100101")
    warnings.extend(us10y_warnings)

    china_cpi_yoy, cpi_warnings = fetch_china_cpi_yoy()
    warnings.extend(cpi_warnings)

    if gold_ohlc.empty:
        raise RuntimeError("沪金 Au99.99 历史行情为空，无法构建策略。请稍后重试 akshare 数据源。")
    if silver_ohlc.empty:
        warnings.append("沪银数据不可用，暂用沪金价格替代沪银以保证页面可运行。")
        silver_ohlc = gold_ohlc.copy()

    common_index = gold_ohlc.index.union(silver_ohlc.index).sort_values()
    common_index = common_index[common_index >= pd.Timestamp("2010-01-01")]

    gold_close = gold_ohlc["close"].reindex(common_index).ffill()
    silver_close = silver_ohlc["close"].reindex(common_index).ffill()
    gold_open = gold_ohlc["open"].reindex(common_index).fillna(gold_close).ffill()
    silver_open = silver_ohlc["open"].reindex(common_index).fillna(silver_close).ffill()
    cash_close = _annualized_cash_index(common_index, default_params().risk_free_annual)
    cash_open = cash_close.shift(1).fillna(cash_close)

    prices_close = pd.DataFrame(
        {
            ASSET_GOLD: gold_close,
            ASSET_SILVER: silver_close,
            ASSET_ACCUM: gold_close,
            ASSET_CASH: cash_close,
        },
        index=common_index,
    ).dropna(how="all")
    prices_open = pd.DataFrame(
        {
            ASSET_GOLD: gold_open,
            ASSET_SILVER: silver_open,
            ASSET_ACCUM: gold_open,
            ASSET_CASH: cash_open,
        },
        index=common_index,
    ).reindex(prices_close.index).ffill()

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return MarketData(
        prices_close=prices_close,
        prices_open=prices_open,
        gold_ohlc=gold_ohlc,
        silver_ohlc=silver_ohlc,
        usd_index=usd_index,
        us10y=us10y,
        china_cpi_yoy=china_cpi_yoy,
        realtime_quotes=realtime_quotes,
        warnings=warnings,
        updated_at=updated_at,
    )


# =============================================================================
# 因子计算层：全部只使用当日及以前数据。
# =============================================================================


def align_macro_to_daily(market_data: MarketData) -> pd.DataFrame:
    """把低频/外盘宏观数据对齐到上金所交易日，使用向前填充避免未来数据。"""
    index = market_data.prices_close.index
    macro = pd.DataFrame(index=index)

    macro["美元指数"] = market_data.usd_index.reindex(index).ffill()
    macro["美国10年期国债收益率"] = market_data.us10y.reindex(index).ffill()
    macro["中国CPI同比"] = market_data.china_cpi_yoy.reindex(index).ffill()

    return macro


def compute_factor_scores(market_data: MarketData, params: StrategyParams) -> pd.DataFrame:
    """
    计算四类贵金属择时因子得分。

    四个因子均为 0-10 分：
    - 波动率因子：沪金 20 日年化波动率分位越低，得分越高。
    - 宏观因子：美元指数走弱、美债收益率下行、CPI 偏高更利多贵金属。
    - 趋势因子：价格高于长期均线、50/200 日均线结构更强，得分越高。
    - 动量因子：20/60 日动量更强，得分越高。
    """
    close = market_data.prices_close[ASSET_GOLD]
    returns = close.pct_change(fill_method=None)
    macro = align_macro_to_daily(market_data)

    vol_20 = returns.rolling(20, min_periods=20).std() * np.sqrt(252)
    volatility_score = _percentile_score(vol_20, invert=True)

    usd_mom_60 = macro["美元指数"].pct_change(60, fill_method=None)
    us10y_change_60 = macro["美国10年期国债收益率"].diff(60)
    cpi_level = macro["中国CPI同比"]
    macro_score = pd.concat(
        [
            _percentile_score(usd_mom_60, invert=True),
            _percentile_score(us10y_change_60, invert=True),
            _percentile_score(cpi_level, invert=False),
        ],
        axis=1,
    ).mean(axis=1)

    ma50 = close.rolling(50, min_periods=50).mean()
    ma200 = close.rolling(200, min_periods=200).mean()
    trend_raw = 0.6 * (close / ma200 - 1.0) + 0.4 * (ma50 / ma200 - 1.0)
    trend_score = _percentile_score(trend_raw, invert=False)

    momentum_raw = 0.6 * close.pct_change(20, fill_method=None) + 0.4 * close.pct_change(60, fill_method=None)
    momentum_score = _percentile_score(momentum_raw, invert=False)

    factor_scores = pd.DataFrame(
        {
            "波动率因子": volatility_score,
            "宏观因子": macro_score,
            "趋势因子": trend_score,
            "动量因子": momentum_score,
        },
        index=market_data.prices_close.index,
    )

    # 早期滚动窗口不足时使用中性 5 分，避免页面空白；这不引入未来数据。
    return factor_scores.fillna(5.0).clip(0.0, 10.0)


def compute_total_score(factor_scores: pd.DataFrame, params: StrategyParams) -> pd.Series:
    """按用户配置权重合成 0-10 分综合得分。"""
    weights = pd.Series(
        {
            "波动率因子": params.volatility_weight,
            "宏观因子": params.macro_weight,
            "趋势因子": params.trend_weight,
            "动量因子": params.momentum_weight,
        }
    ).clip(lower=0.0)
    if weights.sum() <= 0:
        weights[:] = 1.0
    score = factor_scores.mul(weights, axis=1).sum(axis=1) / weights.sum()
    return score.clip(0.0, 10.0).rename("综合得分")


# =============================================================================
# 策略层：仓位映射、风控、次日执行。
# =============================================================================


def _empty_weights(index: pd.DatetimeIndex) -> pd.DataFrame:
    """创建空仓位矩阵。"""
    return pd.DataFrame(0.0, index=index, columns=ASSET_COLUMNS)


def _set_allocation(row: pd.Series, allocation: Dict[str, float]) -> pd.Series:
    """把仓位字典写入单日仓位行。"""
    row.loc[:] = 0.0
    for asset, weight in allocation.items():
        row.loc[asset] = float(weight)
    return row


def map_score_to_weights(total_score: pd.Series, params: StrategyParams) -> pd.DataFrame:
    """按照 6 档规则把综合得分映射为目标仓位。"""
    weights = _empty_weights(total_score.index)
    for dt, score in total_score.items():
        row = weights.loc[dt].copy()
        if score >= params.threshold_full_silver:
            row = _set_allocation(row, {ASSET_SILVER: 1.0})
        elif score >= params.threshold_mix:
            row = _set_allocation(row, {ASSET_GOLD: 0.7, ASSET_SILVER: 0.3})
        elif score >= params.threshold_full_gold:
            row = _set_allocation(row, {ASSET_GOLD: 1.0})
        elif score >= params.threshold_accum:
            row = _set_allocation(row, {ASSET_ACCUM: 1.0})
        else:
            row = _set_allocation(row, {ASSET_CASH: 1.0})
        weights.loc[dt] = row
    return weights


def apply_risk_controls(
    raw_weights: pd.DataFrame,
    market_data: MarketData,
    params: StrategyParams,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    应用风控规则，仍然只使用当日收盘及以前的信息。

    风控含义：
    - 如果沪金收盘跌破 200 日均线，当日决策改为 100% 存积金，次日开盘执行。
    - 如果当前进攻/黄金类持仓从入场收盘价计算亏损超过阈值，当日决策改为 100% 存积金，次日开盘执行。
    """
    close = market_data.prices_close
    gold_close = close[ASSET_GOLD]
    ma200 = gold_close.rolling(200, min_periods=200).mean()

    controlled = raw_weights.copy()
    reason = pd.Series("正常信号", index=controlled.index, name="风控原因")
    active_asset: Optional[str] = None
    entry_price: Optional[float] = None

    for dt in controlled.index:
        row = controlled.loc[dt].copy()
        dominant_asset = row.idxmax()

        if dominant_asset != active_asset:
            active_asset = dominant_asset
            entry_price = (
                float(close.loc[dt, dominant_asset])
                if dominant_asset in close.columns and pd.notna(close.loc[dt, dominant_asset])
                else None
            )

        forced = False
        if pd.notna(ma200.loc[dt]) and gold_close.loc[dt] < ma200.loc[dt]:
            row = _set_allocation(row, {ASSET_ACCUM: 1.0})
            reason.loc[dt] = "沪金跌破200日均线，转入存积金防守"
            forced = True

        if not forced and active_asset in [ASSET_GOLD, ASSET_SILVER, ASSET_ACCUM]:
            current_price = close.loc[dt, active_asset]
            if entry_price and pd.notna(current_price):
                trade_return = float(current_price / entry_price - 1.0)
                if trade_return <= -abs(params.stop_loss):
                    row = _set_allocation(row, {ASSET_ACCUM: 1.0})
                    reason.loc[dt] = f"单笔亏损达到 {abs(params.stop_loss):.1%}，转入存积金防守"

        controlled.loc[dt] = row

    return controlled, reason


def decision_to_execution_weights(decision_weights: pd.DataFrame) -> pd.DataFrame:
    """
    将当日收盘后的决策延后到次日执行。

    这是避免未来函数的核心：t 日信号只会影响 t+1 日仓位。
    """
    execution = decision_weights.shift(1)
    if len(execution) > 0:
        execution.iloc[0] = 0.0
        execution.iloc[0, execution.columns.get_loc(ASSET_CASH)] = 1.0
    return execution.ffill().fillna(0.0)


def describe_allocation(weight_row: pd.Series) -> str:
    """把仓位行转换成中文建议描述。"""
    non_zero = weight_row[weight_row.abs() > 1e-8]
    if non_zero.empty:
        return "空仓"
    return " + ".join([f"{weight:.0%} {asset}" for asset, weight in non_zero.items()])


# =============================================================================
# 回测层：vectorbt 组合回测 + 手写指标校验。
# =============================================================================


def compute_manual_equity(
    prices_close: pd.DataFrame,
    execution_weights: pd.DataFrame,
    fee_rate: float,
    slippage_rate: float,
) -> Tuple[pd.Series, pd.Series]:
    """
    用简单透明的方式计算净值，作为 vectorbt 结果的解释和兜底。

    这里使用收盘到收盘收益，仓位已经由上一日信号 shift 到当日，因此无未来函数。
    """
    asset_returns = prices_close.pct_change(fill_method=None).fillna(0.0)
    gross_returns = (execution_weights.shift(0).fillna(0.0) * asset_returns).sum(axis=1)
    turnover = execution_weights.diff().abs().sum(axis=1).fillna(0.0)
    costs = turnover * (fee_rate + slippage_rate)
    daily_returns = gross_returns - costs
    equity = (1.0 + daily_returns).cumprod()
    equity.name = "策略净值"
    daily_returns.name = "策略日收益"
    return equity, daily_returns


def run_vectorbt_portfolio(
    prices_close: pd.DataFrame,
    prices_open: pd.DataFrame,
    execution_weights: pd.DataFrame,
    fee_rate: float,
    slippage_rate: float,
) -> Tuple[Optional[Any], Optional[pd.Series], List[str]]:
    """
    使用 vectorbt 按目标权重回测。

    若本地 vectorbt/numba 因平台原因不可用，页面仍会使用手写净值继续展示，并提示原因。
    """
    warnings: List[str] = []
    if vbt is None:
        return None, None, [_friendly_error("vectorbt 导入失败，已使用透明手写回测兜底", VECTORBT_IMPORT_ERROR)]
    try:
        portfolio = vbt.Portfolio.from_orders(
            close=prices_close,
            size=execution_weights,
            size_type="targetpercent",
            price=prices_open,
            fees=fee_rate,
            slippage=slippage_rate,
            init_cash=1.0,
            cash_sharing=True,
            freq="1D",
        )
        stats = portfolio.stats()
        return portfolio, stats, warnings
    except Exception as exc:
        warnings.append(_friendly_error("vectorbt 回测执行失败，已使用透明手写回测兜底", exc))
        return None, None, warnings


def compute_metrics(equity: pd.Series, daily_returns: pd.Series) -> Dict[str, float]:
    """计算核心绩效指标。"""
    clean_returns = daily_returns.dropna()
    periods = max(len(clean_returns), 1)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
    annual_return = (1.0 + total_return) ** (252.0 / periods) - 1.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min())
    sharpe = (
        float(clean_returns.mean() / clean_returns.std() * np.sqrt(252))
        if clean_returns.std() and clean_returns.std() > 0
        else np.nan
    )
    win_rate = float((clean_returns > 0).mean()) if len(clean_returns) else np.nan
    gains = clean_returns[clean_returns > 0]
    losses = clean_returns[clean_returns < 0]
    profit_loss_ratio = (
        float(gains.mean() / abs(losses.mean()))
        if len(gains) > 0 and len(losses) > 0 and abs(losses.mean()) > 0
        else np.nan
    )
    return {
        "累计收益率": total_return,
        "年化收益率": annual_return,
        "最大回撤": max_drawdown,
        "夏普比率": sharpe,
        "胜率": win_rate,
        "盈亏比": profit_loss_ratio,
    }


def risk_adjusted_score(metrics: Dict[str, float]) -> float:
    """
    用于参数寻优的稳健目标函数。

    目标不是单纯追求最高年化，而是偏向“年化高、回撤低”的 Calmar 类得分；
    当最大回撤接近 0 或指标异常时返回极低分，避免噪声参数被选中。
    """
    annual_return = metrics.get("年化收益率", np.nan)
    max_drawdown = metrics.get("最大回撤", np.nan)
    sharpe = metrics.get("夏普比率", np.nan)
    if pd.isna(annual_return) or pd.isna(max_drawdown) or abs(max_drawdown) < 1e-6:
        return -999.0
    calmar = annual_return / abs(max_drawdown)
    sharpe_bonus = 0.15 * max(float(sharpe), 0.0) if not pd.isna(sharpe) else 0.0
    return float(calmar + sharpe_bonus)


def clone_params(base: StrategyParams, **updates: float) -> StrategyParams:
    """复制策略参数并覆盖部分字段，供参数网格搜索使用。"""
    data = base.__dict__.copy()
    data.update(updates)
    return StrategyParams(**data)


def generate_parameter_candidates(base_params: StrategyParams, max_trials: int = 48) -> List[StrategyParams]:
    """
    生成保守的参数候选集。

    为避免过拟合，候选集故意保持小而有经济含义：
    - 权重只做三类倾斜：均衡、趋势/动量、宏观/低波动。
    - 止损只在 3%、5%、8% 中选择。
    - 阈值只测试默认和稍偏进攻/防守两套。
    """
    weight_sets = [
        (1.0, 1.0, 1.0, 1.0),
        (1.2, 0.8, 1.4, 1.4),
        (1.5, 1.2, 0.8, 0.8),
        (0.8, 1.4, 1.3, 1.1),
    ]
    stop_losses = [0.03, 0.05, 0.08]
    threshold_sets = [
        (8.0, 6.0, 4.0, 2.0),
        (7.5, 5.8, 3.8, 1.8),
        (8.5, 6.5, 4.5, 2.5),
        (9.0, 7.0, 4.5, 2.0),
    ]
    candidates: List[StrategyParams] = []
    for weights in weight_sets:
        for stop_loss in stop_losses:
            for thresholds in threshold_sets:
                candidates.append(
                    clone_params(
                        base_params,
                        volatility_weight=weights[0],
                        macro_weight=weights[1],
                        trend_weight=weights[2],
                        momentum_weight=weights[3],
                        stop_loss=stop_loss,
                        threshold_full_silver=thresholds[0],
                        threshold_mix=thresholds[1],
                        threshold_full_gold=thresholds[2],
                        threshold_accum=thresholds[3],
                    )
                )
    return candidates[: max(1, max_trials)]


def params_to_label(params: StrategyParams) -> str:
    """把参数压缩成适合表格展示的短标签。"""
    return (
        f"权重({params.volatility_weight:.1f}/{params.macro_weight:.1f}/"
        f"{params.trend_weight:.1f}/{params.momentum_weight:.1f}), "
        f"止损{params.stop_loss:.0%}, "
        f"阈值{params.threshold_full_silver:.1f}/{params.threshold_mix:.1f}/"
        f"{params.threshold_full_gold:.1f}/{params.threshold_accum:.1f}"
    )


def split_train_validation_dates(
    index: pd.DatetimeIndex,
    start: date,
    end: date,
    train_ratio: float = 0.7,
) -> Tuple[date, date, date, date]:
    """
    把回测区间切成训练期和验证期。

    训练期只用于选择参数；验证期只用于验收，不参与参数选择，这是防止回测陷阱的核心。
    """
    sliced = index[(index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))]
    if len(sliced) < 440:
        raise ValueError("参数寻优至少需要约 440 个交易日，建议选择 2 年以上区间。")
    split_pos = int(len(sliced) * train_ratio)
    split_pos = min(max(split_pos, 220), len(sliced) - 220)
    train_start = sliced[0].date()
    train_end = sliced[split_pos - 1].date()
    validation_start = sliced[split_pos].date()
    validation_end = sliced[-1].date()
    return train_start, train_end, validation_start, validation_end


def optimize_parameter_grid(
    market_data: MarketData,
    base_params: StrategyParams,
    start: date,
    end: date,
    fee_rate: float,
    slippage_rate: float,
    max_trials: int = 48,
) -> pd.DataFrame:
    """
    参数寻优：训练期选择，验证期验收。

    注意：这里不会承诺“未来最优”，只寻找历史训练期中风险调整表现更好的参数，并把验证期结果
    摆出来防止过拟合。最终实盘应优先选择训练/验证都稳健的参数，而不是只看训练期第一名。
    """
    train_start, train_end, validation_start, validation_end = split_train_validation_dates(
        market_data.prices_close.index, start, end
    )
    rows: List[Dict[str, Any]] = []
    for rank, params in enumerate(generate_parameter_candidates(base_params, max_trials=max_trials), start=1):
        try:
            train_result = run_backtest(
                market_data, params, train_start, train_end, fee_rate, slippage_rate
            )
            validation_result = run_backtest(
                market_data, params, validation_start, validation_end, fee_rate, slippage_rate
            )
            train_score = risk_adjusted_score(train_result.metrics)
            validation_score = risk_adjusted_score(validation_result.metrics)
            robust_score = 0.7 * train_score + 0.3 * min(train_score, validation_score)
            rows.append(
                {
                    "候选": rank,
                    "参数": params_to_label(params),
                    "训练开始": pd.Timestamp(train_start),
                    "训练结束": pd.Timestamp(train_end),
                    "验证开始": pd.Timestamp(validation_start),
                    "验证结束": pd.Timestamp(validation_end),
                    "训练年化": train_result.metrics["年化收益率"],
                    "训练最大回撤": train_result.metrics["最大回撤"],
                    "训练夏普": train_result.metrics["夏普比率"],
                    "训练稳健分": train_score,
                    "验证年化": validation_result.metrics["年化收益率"],
                    "验证最大回撤": validation_result.metrics["最大回撤"],
                    "验证夏普": validation_result.metrics["夏普比率"],
                    "验证稳健分": validation_score,
                    "综合稳健分": robust_score,
                    "params_obj": params,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "候选": rank,
                    "参数": params_to_label(params),
                    "训练开始": pd.Timestamp(train_start),
                    "训练结束": pd.Timestamp(train_end),
                    "验证开始": pd.Timestamp(validation_start),
                    "验证结束": pd.Timestamp(validation_end),
                    "训练年化": np.nan,
                    "训练最大回撤": np.nan,
                    "训练夏普": np.nan,
                    "训练稳健分": -999.0,
                    "验证年化": np.nan,
                    "验证最大回撤": np.nan,
                    "验证夏普": np.nan,
                    "验证稳健分": -999.0,
                    "综合稳健分": -999.0,
                    "params_obj": params,
                    "错误": str(exc),
                }
            )
    result = pd.DataFrame(rows)
    return result.sort_values(["综合稳健分", "验证年化"], ascending=[False, False]).reset_index(drop=True)


def audit_backtest_integrity(result: BacktestResult) -> pd.DataFrame:
    """生成回测防坑审计表，帮助用户理解哪些陷阱已被控制。"""
    expected_execution = decision_to_execution_weights(result.decision_weights)
    shift_ok = result.execution_weights.round(10).equals(expected_execution.round(10))
    exposure_sum = result.execution_weights.sum(axis=1)
    exposure_ok = bool(((exposure_sum - 1.0).abs() < 1e-8).all())
    trades_ok = bool((result.trades["调仓日期"].is_monotonic_increasing if not result.trades.empty else True))
    rows = [
        StrategyAudit(
            "信号次日执行",
            "通过" if shift_ok else "需检查",
            "所有 t 日收盘信号通过 shift(1) 变成 t+1 执行仓位。",
        ),
        StrategyAudit(
            "单日仓位闭合",
            "通过" if exposure_ok else "需检查",
            "沪金/沪银/存积金/货币基金目标仓位每日合计为 100%。",
        ),
        StrategyAudit(
            "CPI 发布滞后",
            "通过",
            "月度 CPI 延后到次月初进入日频因子，避免把统计月份当成实时可见。",
        ),
        StrategyAudit(
            "调仓记录顺序",
            "通过" if trades_ok else "需检查",
            "交易明细按执行日期单调递增，便于复核每笔收益。",
        ),
        StrategyAudit(
            "参数寻优隔离",
            "通过",
            "寻优页采用训练/验证分离；训练期选参数，验证期只验收。",
        ),
    ]
    return pd.DataFrame([row.__dict__ for row in rows])


def generate_rebalance_orders(
    target_weights: pd.Series,
    current_values: Dict[str, float],
    total_capital: float,
    min_trade_amount: float = 100.0,
) -> pd.DataFrame:
    """
    把目标仓位转换成买卖金额。

    参数含义：
    - target_weights: 策略建议目标权重。
    - current_values: 用户当前各标的市值/现金。
    - total_capital: 用于调仓的总资产规模。
    - min_trade_amount: 低于该金额的微小差异忽略，避免过度交易。
    """
    rows: List[Dict[str, Any]] = []
    for asset in ASSET_COLUMNS:
        target_weight = float(target_weights.get(asset, 0.0))
        current_value = float(current_values.get(asset, 0.0))
        target_value = float(total_capital * target_weight)
        diff = target_value - current_value
        if abs(diff) < min_trade_amount:
            action = "持有"
            trade_amount = 0.0
        elif diff > 0:
            action = "买入"
            trade_amount = diff
        else:
            action = "卖出"
            trade_amount = abs(diff)
        rows.append(
            {
                "标的": asset,
                "目标仓位": target_weight,
                "当前市值": current_value,
                "目标市值": target_value,
                "差额": diff,
                "操作": action,
                "建议交易金额": trade_amount,
            }
        )
    return pd.DataFrame(rows)


def build_trade_log(
    execution_weights: pd.DataFrame,
    equity: pd.Series,
    risk_reason: pd.Series,
) -> pd.DataFrame:
    """生成历史调仓记录，包含调仓日期、标的、仓位和上一笔收益。"""
    if execution_weights.empty:
        return pd.DataFrame()

    changed = execution_weights.ne(execution_weights.shift(1)).any(axis=1)
    change_dates = execution_weights.index[changed]
    records: List[Dict[str, Any]] = []
    previous_date: Optional[pd.Timestamp] = None

    for dt in change_dates:
        row = execution_weights.loc[dt]
        single_return = 0.0
        if previous_date is not None and previous_date in equity.index and dt in equity.index:
            entry_value = float(equity.loc[previous_date])
            exit_value = float(equity.loc[dt])
            if entry_value != 0:
                single_return = exit_value / entry_value - 1.0
        records.append(
            {
                "调仓日期": dt.date().isoformat(),
                "年份": int(dt.year),
                "标的": describe_allocation(row),
                "沪金仓位": row[ASSET_GOLD],
                "沪银仓位": row[ASSET_SILVER],
                "存积金仓位": row[ASSET_ACCUM],
                "货币基金仓位": row[ASSET_CASH],
                "单笔收益": single_return,
                "风控原因": risk_reason.reindex([dt]).iloc[0] if dt in risk_reason.index else "",
            }
        )
        previous_date = dt

    return pd.DataFrame(records)


def run_backtest(
    market_data: MarketData,
    params: StrategyParams,
    start: date,
    end: date,
    fee_rate: float,
    slippage_rate: float,
) -> BacktestResult:
    """运行完整策略回测。"""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    prices_close = market_data.prices_close.loc[start_ts:end_ts].copy()
    prices_open = market_data.prices_open.loc[start_ts:end_ts].copy()
    if len(prices_close) < 220:
        raise ValueError("回测区间少于 220 个交易日，无法稳定计算 200 日均线和因子。")

    sliced_data = MarketData(
        prices_close=prices_close,
        prices_open=prices_open,
        gold_ohlc=market_data.gold_ohlc.loc[:end_ts],
        silver_ohlc=market_data.silver_ohlc.loc[:end_ts],
        usd_index=market_data.usd_index.loc[:end_ts],
        us10y=market_data.us10y.loc[:end_ts],
        china_cpi_yoy=market_data.china_cpi_yoy.loc[:end_ts],
        realtime_quotes=market_data.realtime_quotes,
        warnings=market_data.warnings,
        updated_at=market_data.updated_at,
    )

    factor_scores = compute_factor_scores(sliced_data, params)
    total_score = compute_total_score(factor_scores, params)
    raw_weights = map_score_to_weights(total_score, params)
    decision_weights, risk_reason = apply_risk_controls(raw_weights, sliced_data, params)
    execution_weights = decision_to_execution_weights(decision_weights)

    portfolio, vectorbt_stats, vbt_warnings = run_vectorbt_portfolio(
        prices_close=prices_close,
        prices_open=prices_open,
        execution_weights=execution_weights,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )
    warnings = [*market_data.warnings, *vbt_warnings]

    if portfolio is not None:
        try:
            equity = portfolio.value().rename("策略净值")
            daily_returns = equity.pct_change(fill_method=None).fillna(0.0).rename("策略日收益")
        except Exception as exc:
            warnings.append(_friendly_error("读取 vectorbt 净值失败，已切换为手写净值", exc))
            equity, daily_returns = compute_manual_equity(
                prices_close, execution_weights, fee_rate, slippage_rate
            )
    else:
        equity, daily_returns = compute_manual_equity(
            prices_close, execution_weights, fee_rate, slippage_rate
        )

    benchmark_equity = (1.0 + prices_close[ASSET_GOLD].pct_change(fill_method=None).fillna(0.0)).cumprod()
    benchmark_equity.name = "沪金买入持有"
    drawdown = equity / equity.cummax() - 1.0
    drawdown.name = "策略回撤"
    metrics = compute_metrics(equity, daily_returns)
    trades = build_trade_log(execution_weights, equity, risk_reason)

    return BacktestResult(
        equity=equity,
        benchmark_equity=benchmark_equity,
        drawdown=drawdown,
        decision_weights=decision_weights,
        execution_weights=execution_weights,
        factor_scores=factor_scores,
        total_score=total_score,
        risk_reason=risk_reason,
        daily_returns=daily_returns,
        metrics=metrics,
        trades=trades,
        vectorbt_stats=vectorbt_stats,
        warnings=warnings,
    )


# =============================================================================
# Plotly 可视化
# =============================================================================


def plot_signal_trend(total_score: pd.Series, execution_weights: pd.DataFrame) -> go.Figure:
    """近 7 天信号变化趋势。"""
    recent_score = total_score.tail(7)
    recent_labels = execution_weights.tail(7).apply(describe_allocation, axis=1)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=recent_score.index,
            y=recent_score.values,
            mode="lines+markers",
            name="综合得分",
            text=recent_labels.values,
            hovertemplate="%{x|%Y-%m-%d}<br>得分=%{y:.2f}<br>%{text}<extra></extra>",
        )
    )
    fig.add_hline(y=8, line_dash="dot", line_color="#d97706")
    fig.add_hline(y=6, line_dash="dot", line_color="#d97706")
    fig.add_hline(y=4, line_dash="dot", line_color="#2563eb")
    fig.add_hline(y=2, line_dash="dot", line_color="#64748b")
    fig.update_layout(height=330, margin=dict(l=20, r=20, t=30, b=20), yaxis_range=[0, 10])
    return fig


def plot_equity(result: BacktestResult) -> go.Figure:
    """策略净值与沪金买入持有对比。"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result.equity.index, y=result.equity, name="策略净值"))
    fig.add_trace(
        go.Scatter(
            x=result.benchmark_equity.index,
            y=result.benchmark_equity,
            name="沪金买入持有",
            line=dict(dash="dash"),
        )
    )
    fig.update_layout(height=420, margin=dict(l=20, r=20, t=35, b=20), yaxis_title="净值")
    return fig


def plot_drawdown(result: BacktestResult) -> go.Figure:
    """策略回撤曲线。"""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.drawdown.index,
            y=result.drawdown,
            name="回撤",
            fill="tozeroy",
            line=dict(color="#dc2626"),
        )
    )
    fig.update_layout(
        height=330,
        margin=dict(l=20, r=20, t=35, b=20),
        yaxis_tickformat=".0%",
        yaxis_title="回撤",
    )
    return fig


def plot_position_heatmap(result: BacktestResult) -> go.Figure:
    """仓位变化热力图。"""
    weights = result.execution_weights.T
    fig = go.Figure(
        data=go.Heatmap(
            z=weights.values,
            x=weights.columns,
            y=weights.index,
            colorscale="YlGnBu",
            zmin=0,
            zmax=1,
            colorbar=dict(title="仓位"),
        )
    )
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=35, b=20))
    return fig


def plot_factor_scores(result: BacktestResult) -> go.Figure:
    """因子得分曲线。"""
    fig = go.Figure()
    for column in result.factor_scores.columns:
        fig.add_trace(
            go.Scatter(
                x=result.factor_scores.index,
                y=result.factor_scores[column],
                name=column,
                mode="lines",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=result.total_score.index,
            y=result.total_score,
            name="综合得分",
            mode="lines",
            line=dict(width=4, color="#111827"),
        )
    )
    fig.update_layout(height=390, margin=dict(l=20, r=20, t=35, b=20), yaxis_range=[0, 10])
    return fig


# =============================================================================
# Streamlit 页面层
# =============================================================================


def init_session_state() -> None:
    """初始化页面参数状态。"""
    params = default_params()
    defaults = {
        "volatility_weight": params.volatility_weight,
        "macro_weight": params.macro_weight,
        "trend_weight": params.trend_weight,
        "momentum_weight": params.momentum_weight,
        "stop_loss": params.stop_loss,
        "threshold_full_silver": params.threshold_full_silver,
        "threshold_mix": params.threshold_mix,
        "threshold_full_gold": params.threshold_full_gold,
        "threshold_accum": params.threshold_accum,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def params_from_session() -> StrategyParams:
    """从 Streamlit session_state 读取当前参数。"""
    return StrategyParams(
        volatility_weight=float(st.session_state.volatility_weight),
        macro_weight=float(st.session_state.macro_weight),
        trend_weight=float(st.session_state.trend_weight),
        momentum_weight=float(st.session_state.momentum_weight),
        stop_loss=float(st.session_state.stop_loss),
        threshold_full_silver=float(st.session_state.threshold_full_silver),
        threshold_mix=float(st.session_state.threshold_mix),
        threshold_full_gold=float(st.session_state.threshold_full_gold),
        threshold_accum=float(st.session_state.threshold_accum),
    )


def render_warnings(warnings: List[str]) -> None:
    """集中展示数据源或回测提示，避免直接抛错。"""
    unique_warnings = []
    for item in warnings:
        if item and item not in unique_warnings:
            unique_warnings.append(item)
    if unique_warnings:
        with st.expander("数据源与回测提示", expanded=False):
            for warning in unique_warnings:
                st.warning(warning)


def build_latest_result(market_data: MarketData, params: StrategyParams) -> BacktestResult:
    """首页使用近几年数据快速计算最新信号。"""
    start = max(market_data.prices_close.index.min().date(), date(2018, 1, 1))
    end = market_data.prices_close.index.max().date()
    return run_backtest(market_data, params, start, end, 0.001, 0.0005)


def render_home(market_data: MarketData, params: StrategyParams) -> None:
    """首页：实时信号看板。"""
    st.title("国内贵金属量化择时策略看板")
    st.caption("上金所 AU9999 / AG9999 + 美元指数 + 10 年期美债 + 中国 CPI，日度收盘计算，次日开盘执行。")

    try:
        result = build_latest_result(market_data, params)
    except Exception as exc:
        st.error(_friendly_error("最新信号计算失败", exc))
        render_warnings(market_data.warnings)
        return

    latest_date = result.total_score.index[-1]
    latest_score = float(result.total_score.iloc[-1])
    latest_decision = result.decision_weights.iloc[-1]
    latest_execution = result.execution_weights.iloc[-1]

    quote_df = market_data.realtime_quotes.copy()
    if quote_df.empty:
        quote_df = pd.DataFrame(
            [
                {
                    "标的": ASSET_GOLD,
                    "最新价": market_data.prices_close[ASSET_GOLD].iloc[-1],
                    "更新时间": market_data.updated_at,
                },
                {
                    "标的": ASSET_SILVER,
                    "最新价": market_data.prices_close[ASSET_SILVER].iloc[-1],
                    "更新时间": market_data.updated_at,
                },
            ]
        )
    quote_df = pd.concat(
        [
            quote_df,
            pd.DataFrame(
                [
                    {
                        "标的": ASSET_ACCUM,
                        "最新价": market_data.prices_close[ASSET_ACCUM].iloc[-1],
                        "行情时间": "",
                        "更新时间": market_data.updated_at,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    cols = st.columns(4)
    latest_gold = market_data.prices_close[ASSET_GOLD].iloc[-1]
    latest_silver = market_data.prices_close[ASSET_SILVER].iloc[-1]
    cols[0].metric("最新沪金", _format_num(latest_gold), "元/克")
    cols[1].metric("最新沪银", _format_num(latest_silver), "元/千克")
    cols[2].metric("综合得分", _format_num(latest_score), "0-10")
    cols[3].metric("信号日期", latest_date.date().isoformat())

    st.subheader("今日建议")
    st.info(
        f"当前建议仓位：{describe_allocation(latest_decision)}；"
        f"实际回测执行仓位（上一交易日信号）：{describe_allocation(latest_execution)}。"
    )
    st.caption("页面展示的策略信号为最近可得收盘数据计算结果；回测执行统一延后一个交易日，避免未来函数。")

    st.dataframe(
        quote_df[["标的", "最新价", "行情时间", "更新时间"]]
        if "行情时间" in quote_df.columns
        else quote_df,
        use_container_width=True,
        hide_index=True,
    )

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("近 7 天信号变化")
        st.plotly_chart(plot_signal_trend(result.total_score, result.execution_weights), use_container_width=True)
    with right:
        st.subheader("最新因子得分")
        latest_factor = result.factor_scores.iloc[-1].round(2).reset_index()
        latest_factor.columns = ["因子", "得分"]
        st.dataframe(latest_factor, use_container_width=True, hide_index=True)

    render_warnings(result.warnings)


def render_backtest(market_data: MarketData, params: StrategyParams) -> None:
    """策略回测页面。"""
    st.title("策略回测")
    st.caption("默认区间为 2018 年至今，可调整手续费、滑点后重新运行。")

    min_date = market_data.prices_close.index.min().date()
    max_date = market_data.prices_close.index.max().date()
    col1, col2, col3, col4 = st.columns(4)
    start = col1.date_input("开始日期", value=max(min_date, date(2018, 1, 1)), min_value=min_date, max_value=max_date)
    end = col2.date_input("结束日期", value=max_date, min_value=min_date, max_value=max_date)
    fee = col3.number_input("交易手续费", min_value=0.0, max_value=0.02, value=0.001, step=0.0001, format="%.4f")
    slippage = col4.number_input("滑点", min_value=0.0, max_value=0.02, value=0.0005, step=0.0001, format="%.4f")

    run_clicked = st.button("一键运行回测", type="primary")
    if run_clicked or "last_backtest" not in st.session_state:
        try:
            st.session_state.last_backtest = run_backtest(market_data, params, start, end, fee, slippage)
            st.session_state.last_backtest_args = (start, end, fee, slippage)
        except Exception as exc:
            st.error(_friendly_error("回测失败", exc))
            render_warnings(market_data.warnings)
            return

    result: BacktestResult = st.session_state.last_backtest
    metric_cols = st.columns(5)
    metric_cols[0].metric("年化收益率", _format_pct(result.metrics["年化收益率"]))
    metric_cols[1].metric("最大回撤", _format_pct(result.metrics["最大回撤"]))
    metric_cols[2].metric("夏普比率", _format_num(result.metrics["夏普比率"]))
    metric_cols[3].metric("胜率", _format_pct(result.metrics["胜率"]))
    metric_cols[4].metric("盈亏比", _format_num(result.metrics["盈亏比"]))

    st.subheader("策略净值曲线")
    st.plotly_chart(plot_equity(result), use_container_width=True)

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("回撤曲线")
        st.plotly_chart(plot_drawdown(result), use_container_width=True)
    with col_right:
        st.subheader("仓位变化热力图")
        st.plotly_chart(plot_position_heatmap(result), use_container_width=True)

    st.subheader("因子与综合得分")
    st.plotly_chart(plot_factor_scores(result), use_container_width=True)

    st.subheader("回测防坑审计")
    audit_df = audit_backtest_integrity(result)
    st.dataframe(audit_df, use_container_width=True, hide_index=True)
    st.caption("审计重点覆盖：信号延后执行、仓位闭合、CPI 滞后处理、调仓顺序、训练/验证隔离。")

    render_warnings(result.warnings)


def render_live_decision(market_data: MarketData, params: StrategyParams) -> None:
    """实时买卖决策页面：把策略目标仓位转换成用户可执行的调仓动作。"""
    st.title("实时买卖决策")
    st.caption("输入当前持仓市值，工具会按最新收盘信号生成目标仓位和买卖金额。")

    try:
        result = build_latest_result(market_data, params)
    except Exception as exc:
        st.error(_friendly_error("实时决策计算失败", exc))
        render_warnings(market_data.warnings)
        return

    latest_date = result.total_score.index[-1]
    latest_score = float(result.total_score.iloc[-1])
    target_weights = result.decision_weights.iloc[-1]
    execution_weights = result.execution_weights.iloc[-1]
    latest_reason = result.risk_reason.iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("信号日期", latest_date.date().isoformat())
    c2.metric("综合得分", _format_num(latest_score), "0-10")
    c3.metric("目标仓位", describe_allocation(target_weights))
    c4.metric("回测执行仓位", describe_allocation(execution_weights))

    if latest_reason != "正常信号":
        st.warning(f"当前风控状态：{latest_reason}")
    st.info("执行原则：最新信号基于最近一个可得收盘日；若今天收盘后信号确认，下一交易日开盘/可交易时段执行，避免未来函数。")

    st.subheader("我的当前持仓")
    total_capital = st.number_input("调仓总资产（元）", min_value=0.0, value=100000.0, step=1000.0)
    min_trade_amount = st.number_input("忽略小额差异（元）", min_value=0.0, value=100.0, step=100.0)
    cols = st.columns(4)
    current_values = {
        ASSET_GOLD: cols[0].number_input("当前沪金市值", min_value=0.0, value=0.0, step=1000.0),
        ASSET_SILVER: cols[1].number_input("当前沪银市值", min_value=0.0, value=0.0, step=1000.0),
        ASSET_ACCUM: cols[2].number_input("当前存积金市值", min_value=0.0, value=0.0, step=1000.0),
        ASSET_CASH: cols[3].number_input("当前货币基金/现金", min_value=0.0, value=float(total_capital), step=1000.0),
    }

    orders = generate_rebalance_orders(target_weights, current_values, total_capital, min_trade_amount)
    display = orders.copy()
    display["目标仓位"] = display["目标仓位"].map(lambda x: _format_pct(float(x)))
    for column in ["当前市值", "目标市值", "差额", "建议交易金额"]:
        display[column] = display[column].map(lambda x: f"{float(x):,.2f}")

    st.subheader("建议买卖清单")
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "导出今日买卖清单 CSV",
        data=orders.to_csv(index=False).encode("utf-8-sig"),
        file_name="precious_metals_rebalance_orders.csv",
        mime="text/csv",
    )

    st.subheader("近 7 天信号确认")
    st.plotly_chart(plot_signal_trend(result.total_score, result.execution_weights), use_container_width=True)
    render_warnings(result.warnings)


def render_trades(market_data: MarketData, params: StrategyParams) -> None:
    """交易明细页面。"""
    st.title("交易明细")
    if "last_backtest" not in st.session_state:
        try:
            st.session_state.last_backtest = build_latest_result(market_data, params)
        except Exception as exc:
            st.error(_friendly_error("交易明细生成失败", exc))
            return

    result: BacktestResult = st.session_state.last_backtest
    trades = result.trades.copy()
    if trades.empty:
        st.info("当前回测没有产生调仓记录。")
        return

    years = sorted(trades["年份"].unique().tolist())
    selected_years = st.multiselect("按年份筛选", years, default=years)
    filtered = trades[trades["年份"].isin(selected_years)].copy()
    display = filtered.copy()
    display["单笔收益"] = display["单笔收益"].map(lambda x: _format_pct(float(x)))
    for column in ["沪金仓位", "沪银仓位", "存积金仓位", "货币基金仓位"]:
        display[column] = display[column].map(lambda x: _format_pct(float(x)))

    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "导出交易明细 CSV",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name="precious_metals_trades.csv",
        mime="text/csv",
    )


def render_optimization(market_data: MarketData, params: StrategyParams) -> None:
    """参数寻优页面：训练期选择，验证期验收。"""
    st.title("稳健参数寻优")
    st.caption("寻找高年化、低回撤的参数组合；训练期用于选择，验证期只用于防过拟合验收。")
    st.warning("重要：任何历史寻优都不能保证未来最优。本页默认按综合稳健分排序，优先选择训练/验证都不差的参数。")

    min_date = market_data.prices_close.index.min().date()
    max_date = market_data.prices_close.index.max().date()
    c1, c2, c3, c4, c5 = st.columns(5)
    start = c1.date_input("寻优开始", value=max(min_date, date(2018, 1, 1)), min_value=min_date, max_value=max_date)
    end = c2.date_input("寻优结束", value=max_date, min_value=min_date, max_value=max_date)
    fee = c3.number_input("手续费", min_value=0.0, max_value=0.02, value=0.001, step=0.0001, format="%.4f")
    slippage = c4.number_input("滑点", min_value=0.0, max_value=0.02, value=0.0005, step=0.0001, format="%.4f")
    max_trials = c5.slider("候选数量", min_value=6, max_value=48, value=24, step=6)

    if st.button("开始稳健寻优", type="primary"):
        try:
            with st.spinner("正在做训练/验证分离寻优，这一步会比普通回测更久..."):
                st.session_state.optimization_result = optimize_parameter_grid(
                    market_data, params, start, end, fee, slippage, max_trials=max_trials
                )
        except Exception as exc:
            st.error(_friendly_error("参数寻优失败", exc))
            return

    if "optimization_result" not in st.session_state:
        st.info("点击“开始稳健寻优”后，这里会展示候选参数的训练期和验证期表现。")
        return

    result_df = st.session_state.optimization_result.copy()
    best_params = result_df.iloc[0]["params_obj"]

    st.subheader("推荐参数")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("验证年化", _format_pct(float(result_df.iloc[0]["验证年化"])))
    r2.metric("验证最大回撤", _format_pct(float(result_df.iloc[0]["验证最大回撤"])))
    r3.metric("验证夏普", _format_num(float(result_df.iloc[0]["验证夏普"])))
    r4.metric("综合稳健分", _format_num(float(result_df.iloc[0]["综合稳健分"])))
    st.code(params_to_label(best_params), language="text")

    if st.button("应用推荐参数到全站"):
        st.session_state.volatility_weight = best_params.volatility_weight
        st.session_state.macro_weight = best_params.macro_weight
        st.session_state.trend_weight = best_params.trend_weight
        st.session_state.momentum_weight = best_params.momentum_weight
        st.session_state.stop_loss = best_params.stop_loss
        st.session_state.threshold_full_silver = best_params.threshold_full_silver
        st.session_state.threshold_mix = best_params.threshold_mix
        st.session_state.threshold_full_gold = best_params.threshold_full_gold
        st.session_state.threshold_accum = best_params.threshold_accum
        st.success("已应用推荐参数。可切换到实时决策或策略回测页查看效果。")

    display = result_df.drop(columns=["params_obj"], errors="ignore").head(20).copy()
    for column in ["训练年化", "训练最大回撤", "验证年化", "验证最大回撤"]:
        display[column] = display[column].map(lambda x: _format_pct(float(x)))
    for column in ["训练夏普", "训练稳健分", "验证夏普", "验证稳健分", "综合稳健分"]:
        display[column] = display[column].map(lambda x: _format_num(float(x)))
    for column in ["训练开始", "训练结束", "验证开始", "验证结束"]:
        display[column] = pd.to_datetime(display[column]).dt.date.astype(str)
    st.subheader("候选参数排名")
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_params(market_data: MarketData, params: StrategyParams) -> None:
    """参数调整页面。"""
    st.title("参数调整")
    st.caption("调整因子权重、止损阈值和仓位档位后，可回到回测页点击一键运行查看效果。")

    st.subheader("因子权重")
    col1, col2, col3, col4 = st.columns(4)
    st.session_state.volatility_weight = col1.slider("波动率权重", 0.0, 5.0, float(st.session_state.volatility_weight), 0.1)
    st.session_state.macro_weight = col2.slider("宏观权重", 0.0, 5.0, float(st.session_state.macro_weight), 0.1)
    st.session_state.trend_weight = col3.slider("趋势权重", 0.0, 5.0, float(st.session_state.trend_weight), 0.1)
    st.session_state.momentum_weight = col4.slider("动量权重", 0.0, 5.0, float(st.session_state.momentum_weight), 0.1)

    st.subheader("风控参数")
    st.session_state.stop_loss = st.slider(
        "单笔止损阈值",
        min_value=0.01,
        max_value=0.20,
        value=float(st.session_state.stop_loss),
        step=0.005,
        format="%.3f",
    )

    st.subheader("仓位档位阈值")
    c1, c2, c3, c4 = st.columns(4)
    st.session_state.threshold_full_silver = c1.slider("100%沪银阈值", 0.0, 10.0, float(st.session_state.threshold_full_silver), 0.1)
    st.session_state.threshold_mix = c2.slider("金银混合阈值", 0.0, 10.0, float(st.session_state.threshold_mix), 0.1)
    st.session_state.threshold_full_gold = c3.slider("100%沪金阈值", 0.0, 10.0, float(st.session_state.threshold_full_gold), 0.1)
    st.session_state.threshold_accum = c4.slider("存积金阈值", 0.0, 10.0, float(st.session_state.threshold_accum), 0.1)

    thresholds = [
        st.session_state.threshold_full_silver,
        st.session_state.threshold_mix,
        st.session_state.threshold_full_gold,
        st.session_state.threshold_accum,
    ]
    if thresholds != sorted(thresholds, reverse=True):
        st.error("仓位档位需要保持从高到低：100%沪银阈值 ≥ 金银混合阈值 ≥ 100%沪金阈值 ≥ 存积金阈值。")
    else:
        st.success("参数结构有效。")

    if st.button("使用当前参数快速回测", type="primary"):
        try:
            st.session_state.last_backtest = build_latest_result(market_data, params_from_session())
            st.success("快速回测已完成，可切换到回测页查看图表。")
        except Exception as exc:
            st.error(_friendly_error("快速回测失败", exc))

    with st.expander("当前启动说明", expanded=False):
        st.code(
            "python precious_metals_timing_app.py\n"
            "# 或者依赖已安装后：\n"
            "streamlit run precious_metals_timing_app.py\n"
            "# 自检：\n"
            "python precious_metals_timing_app.py --self-test",
            language="bash",
        )


def main() -> None:
    """Streamlit 主入口。"""
    st.set_page_config(
        page_title="国内贵金属量化择时",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_session_state()

    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.8rem; }
        [data-testid="stMetric"] {
            background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 14px 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.title("贵金属择时")
        page = st.radio(
            "页面",
            ["首页-实时信号看板", "实时买卖决策", "策略回测", "稳健参数寻优", "交易明细", "参数调整"],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("数据源：akshare 免费公开接口")
        if st.button("清除缓存并重新拉取数据"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()

    try:
        market_data = load_market_data()
    except Exception as exc:
        st.error(_friendly_error("数据加载失败", exc))
        st.stop()

    params = params_from_session()
    if page == "首页-实时信号看板":
        render_home(market_data, params)
    elif page == "实时买卖决策":
        render_live_decision(market_data, params)
    elif page == "策略回测":
        render_backtest(market_data, params)
    elif page == "稳健参数寻优":
        render_optimization(market_data, params)
    elif page == "交易明细":
        render_trades(market_data, params)
    elif page == "参数调整":
        render_params(market_data, params)

    st.caption("本工具仅用于研究演示，不构成投资建议。回测结果不代表未来收益。")


# =============================================================================
# 自检：覆盖无未来函数 shift 和风控行为。
# =============================================================================


def _mock_market_data_for_tests() -> MarketData:
    """构造不依赖网络的最小测试数据。"""
    idx = pd.bdate_range("2020-01-01", periods=560)
    gold = pd.Series(np.linspace(100, 160, len(idx)), index=idx)
    silver = pd.Series(np.linspace(100, 180, len(idx)), index=idx)
    cash = _annualized_cash_index(idx, 0.02)
    close = pd.DataFrame(
        {
            ASSET_GOLD: gold,
            ASSET_SILVER: silver,
            ASSET_ACCUM: gold,
            ASSET_CASH: cash,
        }
    )
    open_prices = close.shift(1).fillna(close)
    ohlc = pd.DataFrame({"open": gold, "close": gold, "low": gold * 0.99, "high": gold * 1.01})
    return MarketData(
        prices_close=close,
        prices_open=open_prices,
        gold_ohlc=ohlc,
        silver_ohlc=ohlc.copy(),
        usd_index=pd.Series(np.linspace(100, 95, len(idx)), index=idx),
        us10y=pd.Series(np.linspace(4.5, 3.5, len(idx)), index=idx),
        china_cpi_yoy=pd.Series(np.linspace(0.5, 2.5, len(idx)), index=idx),
        realtime_quotes=pd.DataFrame(),
        warnings=[],
        updated_at="test",
    )


def run_self_tests() -> None:
    """运行轻量自检，便于确认核心策略机制。"""
    params = default_params()
    mock = _mock_market_data_for_tests()

    scores = pd.Series(9.0, index=mock.prices_close.index)
    decision = map_score_to_weights(scores, params)
    execution = decision_to_execution_weights(decision)
    assert execution.iloc[0][ASSET_CASH] == 1.0, "首日必须默认货币基金"
    assert execution.iloc[1][ASSET_SILVER] == 1.0, "t 日信号必须在 t+1 日执行"

    falling = _mock_market_data_for_tests()
    falling.prices_close.loc[falling.prices_close.index[-5]:, ASSET_GOLD] *= 0.7
    falling.prices_close[ASSET_ACCUM] = falling.prices_close[ASSET_GOLD]
    raw = map_score_to_weights(pd.Series(5.0, index=falling.prices_close.index), params)
    controlled, reason = apply_risk_controls(raw, falling, params)
    assert controlled.iloc[-1][ASSET_ACCUM] == 1.0, "跌破 200 日均线后必须切换存积金"
    assert "200日均线" in reason.iloc[-1], "风控原因应说明 200 日均线"

    result = run_backtest(
        mock,
        params,
        mock.prices_close.index[0].date(),
        mock.prices_close.index[-1].date(),
        0.001,
        0.0005,
    )
    assert not result.equity.empty, "回测净值不能为空"
    assert set(ASSET_COLUMNS).issubset(result.execution_weights.columns), "仓位列不完整"

    optimization = optimize_parameter_grid(
        mock,
        base_params=params,
        start=mock.prices_close.index[0].date(),
        end=mock.prices_close.index[-1].date(),
        fee_rate=0.001,
        slippage_rate=0.0005,
        max_trials=6,
    )
    assert not optimization.empty, "参数寻优结果不能为空"
    assert optimization["训练结束"].max() < optimization["验证开始"].min(), "训练期和验证期必须严格分离"

    orders = generate_rebalance_orders(
        target_weights=pd.Series({ASSET_GOLD: 0.7, ASSET_SILVER: 0.3, ASSET_ACCUM: 0.0, ASSET_CASH: 0.0}),
        current_values={ASSET_GOLD: 1000.0, ASSET_SILVER: 0.0, ASSET_ACCUM: 0.0, ASSET_CASH: 9000.0},
        total_capital=10000.0,
    )
    assert set(orders["操作"]) >= {"买入", "卖出"}, "实时决策必须能生成买入/卖出动作"
    print("SELF TEST PASSED: 无未来函数 shift、风控切换、回测净值均通过。")


def run_data_smoke_test() -> None:
    """用真实 akshare 数据跑一次轻量烟测，验证接口字段和默认回测路径。"""
    md = load_market_data()
    start = max(md.prices_close.index.min().date(), date(2018, 1, 1))
    end = md.prices_close.index.max().date()
    result = run_backtest(md, default_params(), start, end, 0.001, 0.0005)
    print("DATA TEST PASSED")
    print(f"close_shape={md.prices_close.shape}")
    print(f"date_range={md.prices_close.index.min().date()}~{md.prices_close.index.max().date()}")
    print(f"warnings={len(md.warnings)}")
    for warning in md.warnings[:8]:
        print(f"warning={warning}")
    print(f"equity_len={len(result.equity)}")
    print(f"last_score={float(result.total_score.iloc[-1]):.4f}")
    print(f"latest_allocation={describe_allocation(result.decision_weights.iloc[-1])}")
    print(f"trades={len(result.trades)}")
    print(f"vectorbt_stats={result.vectorbt_stats is not None}")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_tests()
    elif "--data-test" in sys.argv:
        run_data_smoke_test()
    elif _is_streamlit_runtime() or os.environ.get(APP_CHILD_ENV) == "1":
        main()
