"""확정봉 종가 → 필터 특징과 기준선 추가 특징. 제안서 ②·③·④ 참조.

모든 함수는 시간순으로 정렬된 UTC DatetimeIndex의 종가 Series를 받는다.
창이 누락 봉을 넘지 않도록 segment_ids로 구간을 나눈 뒤 구간별로 계산한다.
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

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


def d_rel_many(close, kernels, bar=BAR):
    """여러 커널의 D̃를 한 번에 계산한다. 열 순서는 kernels의 순서다.

    kernel_features(...)["d_rel"]과 같은 값을 행렬 곱 한 번으로 얻는다.
    """
    check_close(close)
    k = np.asarray(kernels, dtype=float)
    n = k.shape[1]
    seg = segment_ids(close.index, bar)
    out = np.full((len(close), len(k)), np.nan)
    pos = 0
    for _, part in close.groupby(seg):
        x = np.log(part).diff().abs().to_numpy()
        if len(x) >= n:
            win = sliding_window_view(x, n)          # 과거→현재
            simple = win.mean(axis=1)
            weighted = win @ k[:, ::-1].T
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = (weighted - simple[:, None]) / np.where(simple > 0, simple, np.nan)[:, None]
            out[pos + n - 1:pos + len(x)] = rel
        pos += len(part)
    return pd.DataFrame(out, index=close.index)


# ── 기준선 A: ATR(14)/종가, 종가/VIDYA−1, 거래량/20봉 평균 ────────────────────
# ATR은 Pine ta.atr와 같은 Wilder 평활(첫 값은 TR의 단순평균)이다.
# VIDYA는 Chande 표준식이다: k = |CMO(cmo_len)|/100, α = 2/(length+1),
# V[t] = α·k·C[t] + (1 − α·k)·V[t−1], 초깃값은 CMO가 처음 정의되는 봉의 종가.
# 사용 중인 VIDYA 버전이 다르면 이 함수만 바꾸면 된다(모든 군이 같은 값을 공유한다).

def _wilder(values, length):
    out = np.full(len(values), np.nan)
    if len(values) >= length and not np.isnan(values[:length]).any():
        out[length - 1] = values[:length].mean()
        for i in range(length, len(values)):
            out[i] = (out[i - 1] * (length - 1) + values[i]) / length
    return out


def _atr(part, length):
    prev = part["close"].shift()
    tr = pd.concat([part["high"] - part["low"],
                    (part["high"] - prev).abs(),
                    (part["low"] - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = part["high"].iloc[0] - part["low"].iloc[0]
    return pd.Series(_wilder(tr.to_numpy(), length), index=part.index)


def _vidya(close, length, cmo_len):
    c = close.to_numpy()
    d = np.diff(c, prepend=np.nan)
    up = pd.Series(np.where(d > 0, d, 0.0)).rolling(cmo_len).sum().to_numpy().copy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).rolling(cmo_len).sum().to_numpy().copy()
    up[:cmo_len] = np.nan                      # 첫 차분은 정의되지 않는다
    dn[:cmo_len] = np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(up + dn > 0, np.abs(up - dn) / (up + dn), 0.0)
    k[np.isnan(up)] = np.nan
    alpha = 2.0 / (length + 1.0)
    out = np.full(len(c), np.nan)
    for i in range(len(c)):
        if np.isnan(k[i]):
            continue
        prev = c[i] if i == 0 or np.isnan(out[i - 1]) else out[i - 1]
        out[i] = alpha * k[i] * c[i] + (1.0 - alpha * k[i]) * prev
    return pd.Series(out, index=close.index)


def _core_one(part, atr_len, vidya_len, cmo_len, vol_len):
    vol_mean = part["volume"].rolling(vol_len, min_periods=vol_len).mean()
    return pd.DataFrame({
        "atr_rel": _atr(part, atr_len) / part["close"],
        "vidya_rel": part["close"] / _vidya(part["close"], vidya_len, cmo_len) - 1.0,
        "vol_rel": part["volume"] / vol_mean.where(vol_mean > 0),
    })


def baseline_core(bars, atr_len=14, vidya_len=14, cmo_len=9, vol_len=20, bar=BAR):
    """기준선 A의 세 특징. bars는 open·high·low·close·volume 열을 가진다."""
    check_close(bars["close"])
    seg = segment_ids(bars.index, bar)
    parts = [_core_one(part, atr_len, vidya_len, cmo_len, vol_len)
             for _, part in bars.groupby(seg)]
    return pd.concat(parts).reindex(bars.index)
