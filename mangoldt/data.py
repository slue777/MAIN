"""봉 데이터 읽기와 정합성 검사. 제안서 ② 참조."""
import hashlib

import pandas as pd

from .features import BAR

COLUMNS = ["open", "high", "low", "close", "volume"]


def validate_bars(bars):
    """정렬·중복·가격·거래량·OHLC 모순을 검사한다. 문제가 있으면 ValueError."""
    problems = []
    if bars.index.tz is None:
        problems.append("index is not timezone-aware")
    if bars.index.has_duplicates:
        problems.append(f"{int(bars.index.duplicated().sum())} duplicate timestamps")
    if not bars.index.is_monotonic_increasing:
        problems.append("index is not sorted")
    missing = [c for c in COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    prices = bars[["open", "high", "low", "close"]]
    if prices.isna().any().any() or bars["volume"].isna().any():
        problems.append("missing values")
    if (prices <= 0).any().any():
        problems.append("non-positive prices")
    if (bars["volume"] < 0).any():
        problems.append("negative volume")
    body_high = bars[["open", "close"]].max(axis=1)
    body_low = bars[["open", "close"]].min(axis=1)
    bad = (bars["high"] < body_high) | (bars["low"] > body_low)
    if bad.any():
        problems.append(f"{int(bad.sum())} bars with inconsistent OHLC")
    if problems:
        raise ValueError("invalid bars: " + "; ".join(problems))
    return bars


def read_bars(path, time_column="time", index_is_close=False, now=None, bar=BAR):
    """CSV → 검증된 봉. 인덱스는 UTC 봉 시작 시각이다.

    time 열은 ISO 문자열이나 밀리초 epoch 정수를 받는다. index_is_close가 참이면
    마감 시각으로 보고 bar만큼 당긴다. now를 주면 그 시각까지 마감되지 않은 봉을 뺀다.
    """
    raw = pd.read_csv(path)
    t = raw[time_column]
    unit = "ms" if pd.api.types.is_numeric_dtype(t) else None
    index = pd.DatetimeIndex(pd.to_datetime(t, unit=unit, utc=True), name="time")
    bars = raw.drop(columns=[time_column]).set_axis(index).sort_index()
    if index_is_close:
        bars.index = bars.index - bar
    if now is not None:
        bars = bars[bars.index + bar <= pd.Timestamp(now)]
    return validate_bars(bars[COLUMNS].astype(float))


def data_hash(bars):
    """실행 기록에 남길 데이터 해시."""
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(bars, index=True).to_numpy().tobytes())
    return digest.hexdigest()
