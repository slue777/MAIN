"""목표값 RV6와 이진 라벨. 제안서 ② 참조."""
import numpy as np
import pandas as pd

from .features import BAR, check_close, segment_ids

HORIZON = 6


def forward_rv(close, horizon=HORIZON, bar=BAR):
    """RV[t] = Σ r[t+j]², j = 1..horizon. 구간 끝 horizon봉은 결측이다."""
    check_close(close)
    seg = segment_ids(close.index, bar)

    def one(part):
        r2 = np.log(part).diff() ** 2
        return r2.rolling(horizon, min_periods=horizon).sum().shift(-horizon)

    parts = [one(part) for _, part in close.groupby(seg)]
    return pd.concat(parts).reindex(close.index).rename(f"rv{horizon}_fwd")


def fit_threshold(train_rv, quantile=0.75):
    """학습 구간에서 완결된 목표값의 분위수 q.

    라벨 종료 시각이 평가 시작 시각 이상인 행을 빼는 일은 호출하는 쪽의 책임이다.
    """
    done = train_rv.dropna()
    if done.empty:
        raise ValueError("no completed targets in the training range")
    return float(done.quantile(quantile))


def binary_label(rv, q):
    """RV > q이면 1. 목표값이 결측인 행은 결측으로 남긴다."""
    return (rv > q).astype(float).where(rv.notna()).rename("label")
