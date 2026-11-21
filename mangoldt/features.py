"""확정봉 종가 → 필터 특징과 기준선 추가 특징. 제안서 ②·③·④ 참조.

모든 함수는 시간순으로 정렬된 UTC DatetimeIndex의 종가 Series를 받는다.
창이 누락 봉을 넘지 않도록 segment_ids로 구간을 나눈 뒤 구간별로 계산한다.
"""
import numpy as np
import pandas as pd

BAR = pd.Timedelta(hours=4)


def segment_ids(index, bar=BAR):
    """봉 간격이 bar와 다른 지점에서 구간을 끊어 구간 ID를 돌려준다."""
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("index must be strictly increasing")
    step = pd.Series(index, index=index).diff()
    return (step != bar).cumsum().sub(1).rename("segment")


def check_close(close):
    """빈 입력과 비양수 종가를 거부한다. 결측 종가는 허용하며 창을 결측으로 만든다."""
    if close.empty:
        raise ValueError("close is empty")
    if (close <= 0).any():
        raise ValueError("close must be positive")


def _per_segment(close, func, bar):
    check_close(close)
    seg = segment_ids(close.index, bar)
    parts = [func(part) for _, part in close.groupby(seg)]
    return pd.concat(parts).reindex(close.index)


def _kernel_one(close, w):
    x = np.log(close).diff().abs()
    n = len(w)
    window = x.rolling(n, min_periods=n)
    weighted = window.apply(lambda values: values @ w[::-1], raw=True)
    simple = window.mean()
    diff = weighted - simple
    return pd.DataFrame({"weighted": weighted, "sma": simple, "diff": diff,
                         "d_rel": diff / simple.where(simple > 0)})


def kernel_features(close, w, bar=BAR):
    """F(weighted), S(sma), D(diff), D̃(d_rel). S = 0이면 D̃는 결측이다."""
    return _per_segment(close, lambda part: _kernel_one(part, w), bar)


def _extras_one(close):
    r2 = np.log(close).diff() ** 2
    return pd.DataFrame({"rv1": r2,
                         "rv6": r2.rolling(6, min_periods=6).mean(),
                         "rv42": r2.rolling(42, min_periods=42).mean()})


def bar_slot(index, index_is_close=False, bar=BAR):
    """UTC 봉 시작 시각 기준 하루 중 슬롯 번호(4시간봉이면 0–5)."""
    if index.tz is None:
        raise ValueError("index must be timezone-aware (UTC)")
    start = index.tz_convert("UTC")
    if index_is_close:
        start = start - bar
    seconds = start.hour * 3600 + start.minute * 60 + start.second
    return pd.Series(seconds // int(bar.total_seconds()), index=index, name="slot")


def baseline_extras(close, index_is_close=False, bar=BAR):
    """M0에 추가되는 rv1·rv6·rv42와 slot."""
    out = _per_segment(close, _extras_one, bar)
    out["slot"] = bar_slot(close.index, index_is_close, bar)
    return out
