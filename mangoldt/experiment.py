"""비교 실험: 특징 표 구성, 시간 분할, 스텀프 분류기 적합, 확률 출력. 제안서 ④·⑤ 참조.

모형군
  M0   기준 특징 12열 (ATR·VIDYA·거래량·rv1·rv6·rv42·slot 지시변수 6개)
  B    M0 + D̃(폰 망골트)
  W    M0 + D̃(바퀴 커널)
  C    M0 + D̃(전역 순열 커널), n_masks개
  Cp   M0 + D̃(잔여류 보존 순열 커널), n_masks개
  S    M0 + S̃                      (보조)
  SD   M0 + S̃ + D̃(폰 망골트)        (보조)

B·W·C·Cp·S는 특징 수가 같아 같은 시드에서 스텀프 계획을 공유한다. 기준 12열에
걸린 스텀프는 이들 사이에서 완전히 같고, 13번째 열에 걸린 스텀프만 다르다.
"""
import re
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import stump
from .features import BAR, baseline_core, baseline_extras, d_rel_many, kernel_features
from .kernels import control_kernels, mangoldt_weights, wheel_weights
from .labels import fit_threshold, forward_rv

BASE = ["atr_rel", "vidya_rel", "vol_rel", "rv1", "rv6", "rv42"]
SLOTS = [f"slot{i}" for i in range(6)]
M0 = BASE + SLOTS
MAIN_ARMS = ["M0", "B", "W", "S", "SD"]
CONTROL = re.compile(r"Cp?\d+")


@dataclass(frozen=True)
class Config:
    n: int = 64
    horizon: int = 6
    quantile: float = 0.75
    init_frac: float = 0.5
    n_folds: int = 4
    n_trees: int = 300
    n_tries: int = 10
    seeds: tuple = (42, 43, 44, 45, 46)
    n_masks: int = 200
    mask_seed_c: int = 1001
    mask_seed_cp: int = 1002
    period: int = 6

    def record(self):
        return asdict(self)


def build_frame(bars, cfg=Config(), bar=BAR):
    """봉 → (특징·목표값 표, 커널 표). 표의 인덱스는 UTC 봉 시작 시각이다."""
    close = bars["close"]
    w = mangoldt_weights(cfg.n)
    c = control_kernels(w, cfg.n_masks, cfg.mask_seed_c)
    cp = control_kernels(w, cfg.n_masks, cfg.mask_seed_cp, period=cfg.period)
    names = (["B", "W"] + [f"C{i:03d}" for i in range(cfg.n_masks)]
             + [f"Cp{i:03d}" for i in range(cfg.n_masks)])
    kernels = pd.DataFrame(np.array([w, wheel_weights(cfg.n)] + c + cp), index=names)

    extras = baseline_extras(close, bar=bar)
    frame = pd.concat([baseline_core(bars, bar=bar), extras[["rv1", "rv6", "rv42"]]], axis=1)
    for i, name in enumerate(SLOTS):
        frame[name] = (extras["slot"] == i).astype(float)
    sma = kernel_features(close, w, bar)["sma"]
    root = np.sqrt(extras["rv42"])
    frame["S"] = sma / root.where(root > 0)
    arms = d_rel_many(close, kernels.to_numpy(), bar).set_axis(names, axis=1)
    frame = pd.concat([frame, arms], axis=1)
    frame["target"] = forward_rv(close, cfg.horizon, bar)
    frame["label_end"] = frame.index + (cfg.horizon + 1) * bar   # t+horizon 봉의 마감 시각
    return frame, kernels


def folds(frame, cfg=Config()):
    """확장 창 분할. (폴드 번호, 학습 행, 평가 행)을 차례로 낸다.

    평가 행은 모든 군의 특징과 목표값이 있는 행이다. 학습 행은 그중 라벨 종료
    시각이 평가 시작 시각보다 이른 행이다.
    """
    arm_cols = [c for c in frame.columns if c not in ("target", "label_end")]
    valid = frame[arm_cols].notna().all(axis=1) & frame["target"].notna()
    n = len(frame)
    edges = np.linspace(int(n * cfg.init_frac), n, cfg.n_folds + 1).astype(int)
    pos = np.arange(n)
    for k in range(cfg.n_folds):
        start = frame.index[edges[k]]
        train = valid & (pos < edges[k]) & (frame["label_end"] < start)
        evaluate = valid & (pos >= edges[k]) & (pos < edges[k + 1])
        if not train.any() or not evaluate.any():
            raise ValueError(f"fold {k} has no usable training or evaluation rows")
        yield k, train.to_numpy(), evaluate.to_numpy()


def _fit_fold(frame, train, evaluate, q, seed, cfg, control_names):
    y = (frame["target"].to_numpy()[train] > q).astype(float)
    ns = int(train.sum())

    def split(col):
        v = frame[col].to_numpy()
        return v[train], v[evaluate]

    def forest(cols):
        feats, rows = stump.make_plan(seed, cfg.n_trees, len(cols), ns, cfg.n_tries)
        return [_votes(split(c), y, rows[feats == i]) for i, c in enumerate(cols)]

    out = {"M0": sum(forest(M0)) / cfg.n_trees}
    out["SD"] = sum(forest(M0 + ["S", "B"])) / cfg.n_trees

    feats, rows = stump.make_plan(seed, cfg.n_trees, len(M0) + 1, ns, cfg.n_tries)
    shared = sum(_votes(split(c), y, rows[feats == i]) for i, c in enumerate(M0))
    extra_rows = rows[feats == len(M0)]
    for name in ["B", "W", "S"] + control_names:
        xtr, xev = split(name)
        out[name] = (shared + stump.column_votes(xtr, y, extra_rows, xev)) / cfg.n_trees
    return float(y.mean()), out


def _votes(pair, y, rows):
    return stump.column_votes(pair[0], y, rows, pair[1])


def run(frame, cfg=Config()):
    """모든 폴드·시드를 적합한다.

    돌려주는 값
      predictions  주 모형군의 행별 확률 (time, fold, arm, seed, q, target, label, base_prob, prob)
                   base_prob는 학습 구간의 사건 비율이다
      controls     대조 마스크별 폴드·시드 평균 제곱오차 합과 표본 수
    """
    control_names = [c for c in frame.columns if CONTROL.fullmatch(c)]
    pred_parts, ctrl_parts = [], []
    for k, train, evaluate in folds(frame, cfg):
        q = fit_threshold(frame["target"][train], cfg.quantile)
        target = frame["target"].to_numpy()[evaluate]
        label = (target > q).astype(float)
        times = frame.index[evaluate]
        sq = {name: np.zeros(len(label)) for name in control_names}
        for seed in cfg.seeds:
            base, probs = _fit_fold(frame, train, evaluate, q, seed, cfg, control_names)
            for arm in MAIN_ARMS:
                pred_parts.append(pd.DataFrame({
                    "time": times, "fold": k, "arm": arm, "seed": seed, "q": q,
                    "target": target, "label": label, "base_prob": base, "prob": probs[arm]}))
            for name in control_names:
                sq[name] += (probs[name] - label) ** 2 / len(cfg.seeds)
        ctrl_parts.append(pd.DataFrame({
            "fold": k, "mask": control_names, "n": len(label),
            "sq_sum": [sq[name].sum() for name in control_names]}))
    return pd.concat(pred_parts, ignore_index=True), pd.concat(ctrl_parts, ignore_index=True)
