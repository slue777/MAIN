"""커널 생성: 폰 망골트, 바퀴(W), 전역 순열(C), 잔여류 보존 순열(C′).

가중치 배열의 위치 j는 시차다(j = 0이 현재 봉). 제안서 ③·④ 참조.
"""
import math

import numpy as np


def mangoldt_raw(n=64):
    """Λ(k), k = 1..n을 위치 k−1에 담아 돌려준다(정규화 전)."""
    if n < 2:
        raise ValueError("n must be at least 2")
    raw = np.zeros(n)
    for p in range(2, n + 1):
        if any(p % d == 0 for d in range(2, math.isqrt(p) + 1)):
            continue
        k = p
        while k <= n:
            raw[k - 1] = math.log(p)
            k *= p
    return raw


def mangoldt_weights(n=64):
    raw = mangoldt_raw(n)
    return raw / raw.sum()


def wheel_weights(n=64):
    """2·3의 거듭제곱에는 Λ를 두고, 6과 서로소인 k ≥ 5 전부에 ln k를 준다."""
    raw = mangoldt_raw(n)
    for k in range(5, n + 1):
        if math.gcd(k, 6) == 1:
            raw[k - 1] = math.log(k)
    return raw / raw.sum()


def centroid(w):
    return float(np.arange(len(w)) @ w)


def residue_shares(w, period=6):
    lag = np.arange(len(w))
    return np.array([w[lag % period == r].sum() for r in range(period)])


def control_kernels(w, count, seed, period=None, tol=0.5, max_tries=1_000_000):
    """w[0]을 고정하고 나머지 가중치를 섞은 서로 다른 커널 count개를 만든다.

    period가 None이면 전역 순열(C), 정수면 시차 mod period가 같은 위치끼리만
    섞는 잔여류 보존 순열(C′)이다. 무게중심이 원 커널에서 ±tol봉 이내인
    배열만 채택한다.
    """
    rng = np.random.default_rng(seed)
    lag = np.arange(len(w))
    if period is None:
        groups = [lag[1:]]
    else:
        groups = [lag[(lag % period == r) & (lag > 0)] for r in range(period)]
    target = lag @ w
    found = {}
    for _ in range(max_tries):
        if len(found) >= count:
            break
        k = w.copy()
        for g in groups:
            k[g] = rng.permutation(w[g])
        if abs(lag @ k - target) <= tol and not np.allclose(k, w):
            found.setdefault(k.tobytes(), k)
    if len(found) < count:
        raise RuntimeError(
            f"only {len(found)} of {count} control kernels found in {max_tries} tries")
    return list(found.values())
