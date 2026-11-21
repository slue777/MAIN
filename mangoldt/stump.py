"""RF형 스텀프 분류기. Pine 지표 "GainzAlgo | Rust Stump"의 trainClassifier /
predictProb를 그대로 옮긴 것이다.

- 난수: Park–Miller LCG (state·48271 mod 2³¹−1), pick = ⌊state / (2³¹−1) · bound⌋
- 스텀프마다 특징 하나를 뽑고, 무작위 학습 행의 특징값을 임계값 후보로 n_tries번
  뽑아 지니 이득이 가장 큰 것을 고른다(동률이면 먼저 나온 후보).
- 분할은 값 ≤ 임계값이면 왼쪽. 잎의 값은 그 쪽의 양성 비율.
- 유효한 분할이 하나도 없으면 임계값은 첫 학습 행의 값, 양쪽 확률은 0.5.
- 예측은 모든 스텀프의 잎 확률 평균.

난수 추출 순서가 데이터와 무관하므로, 특징 수와 학습 행 수가 같은 모델들은
같은 시드에서 같은 (특징, 후보 행) 계획을 공유한다. 실험은 이 성질을 이용해
한 열만 다른 모델들을 짝지어 비교한다.
"""
import numpy as np

MODULUS = 2147483647
MULTIPLIER = 48271


class Sampler:
    def __init__(self, seed):
        if not 1 <= seed < MODULUS:
            raise ValueError("seed must be in [1, 2**31 - 2]")
        self.state = int(seed)

    def pick(self, bound):
        self.state = (self.state * MULTIPLIER) % MODULUS
        return int(np.floor(self.state / float(MODULUS) * bound))


def make_plan(seed, n_trees, n_features, n_samples, n_tries=10):
    """(스텀프별 특징 번호, 스텀프별 임계값 후보 행 번호[n_tries])."""
    sampler = Sampler(seed)
    feats = np.empty(n_trees, dtype=int)
    rows = np.empty((n_trees, n_tries), dtype=int)
    for i in range(n_trees):
        feats[i] = sampler.pick(n_features)
        for t in range(n_tries):
            rows[i, t] = sampler.pick(n_samples)
    return feats, rows


def fit_column(x, y, rows):
    """한 특징 열에 대해 rows(스텀프 수 × n_tries)의 스텀프를 한꺼번에 적합한다.

    돌려주는 값은 (임계값, 왼쪽 확률, 오른쪽 확률) 배열이다.
    """
    ns = len(y)
    total = float(y.sum())
    p = total / ns
    gini_base = 1.0 - p * p - (1.0 - p) * (1.0 - p)
    order = np.argsort(x, kind="stable")
    xs = x[order]
    cum = np.concatenate([[0.0], np.cumsum(y[order])])
    thr = x[rows]
    lt = np.searchsorted(xs, thr, side="right").astype(float)
    lb = cum[lt.astype(int)]
    rt = ns - lt
    rb = total - lb
    valid = (lt > 0) & (rt > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pl = lb / lt
        pr = rb / rt
        gl = 1.0 - pl * pl - (1.0 - pl) * (1.0 - pl)
        gr = 1.0 - pr * pr - (1.0 - pr) * (1.0 - pr)
        gain = gini_base - (lt * gl + rt * gr) / ns
    gain = np.where(valid, gain, -np.inf)
    best = gain.argmax(axis=1)
    take = np.arange(len(rows))
    ok = valid.any(axis=1)
    return (np.where(ok, thr[take, best], x[0]),
            np.where(ok, pl[take, best], 0.5),
            np.where(ok, pr[take, best], 0.5))


def column_votes(x_train, y, rows, x_eval):
    """한 열의 스텀프들이 평가 행마다 내는 잎 확률의 합."""
    if len(rows) == 0:
        return np.zeros(len(x_eval))
    thr, pl, pr = fit_column(x_train, y, rows)
    return np.where(x_eval[:, None] <= thr[None, :], pl[None, :], pr[None, :]).sum(axis=1)


def predict_proba(x_train, y, x_eval, seed, n_trees=30, n_tries=10):
    """학습 후 평가 행의 양성 확률. 입력에 결측이 없어야 한다."""
    x_train = np.asarray(x_train, dtype=float)
    x_eval = np.asarray(x_eval, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(y) == 0 or x_train.shape[1] == 0:
        raise ValueError("training data is empty")
    if np.isnan(x_train).any() or np.isnan(x_eval).any() or np.isnan(y).any():
        raise ValueError("inputs must not contain NaN")
    feats, rows = make_plan(seed, n_trees, x_train.shape[1], len(y), n_tries)
    votes = np.zeros(len(x_eval))
    for f in np.unique(feats):
        votes += column_votes(x_train[:, f], y, rows[feats == f], x_eval[:, f])
    return votes / n_trees
