"""평가: 확률 지표, 짝지은 ΔBrier, 블록 부트스트랩, 순위 p값, 판정. 제안서 ⑤ 참조."""
import numpy as np
import pandas as pd

CLIP = 1e-15
BINS = 10


def brier(prob, label):
    return float(np.mean((prob - label) ** 2))


def log_loss(prob, label):
    p = np.clip(prob, CLIP, 1 - CLIP)
    return float(-np.mean(label * np.log(p) + (1 - label) * np.log(1 - p)))


def calibration_table(prob, label):
    """10구간(경계 0.1 간격, 1.0은 마지막 구간)별 표본 수·예측 평균·관측 빈도."""
    bucket = np.minimum(BINS - 1, (np.asarray(prob) * BINS).astype(int))
    rows = []
    for b in range(BINS):
        m = bucket == b
        rows.append({"bin": b, "n": int(m.sum()),
                     "mean_prob": float(prob[m].mean()) if m.any() else np.nan,
                     "observed": float(label[m].mean()) if m.any() else np.nan})
    return pd.DataFrame(rows)


def ece(prob, label):
    t = calibration_table(prob, label)
    t = t[t["n"] > 0]
    return float((t["n"] * (t["mean_prob"] - t["observed"]).abs()).sum() / t["n"].sum())


def run_metrics(predictions):
    """실행(폴드·모형군·시드)별 지표. base_brier는 학습 구간 사건 비율을 그대로 낸 경우다."""
    rows = []
    for (fold, arm, seed), g in predictions.groupby(["fold", "arm", "seed"]):
        p, y = g["prob"].to_numpy(), g["label"].to_numpy()
        rows.append({"fold": fold, "arm": arm, "seed": seed, "n": len(g),
                     "event_rate": float(y.mean()), "brier": brier(p, y),
                     "base_brier": brier(g["base_prob"].to_numpy(), y),
                     "log_loss": log_loss(p, y), "ece": ece(p, y)})
    return pd.DataFrame(rows)


def paired_loss(predictions):
    """시각별·모형군별 제곱오차(시드 평균). 열은 모형군, 행은 (fold, time)."""
    sq = predictions.assign(sq=(predictions["prob"] - predictions["label"]) ** 2)
    return sq.groupby(["fold", "time", "arm"])["sq"].mean().unstack("arm").sort_index()


def block_bootstrap_mean(values, fold, block, n_boot=2000, seed=7):
    """폴드 안에서 연속 블록을 재표집한 전체 평균의 분포."""
    rng = np.random.default_rng(seed)
    groups = [values[fold == f] for f in np.unique(fold)]
    total = sum(len(g) for g in groups)
    out = np.empty(n_boot)
    for b in range(n_boot):
        acc = 0.0
        for g in groups:
            size = min(block, len(g))
            starts = rng.integers(0, len(g) - size + 1, int(np.ceil(len(g) / size)))
            idx = (starts[:, None] + np.arange(size)[None, :]).ravel()[:len(g)]
            acc += g[idx].sum()
        out[b] = acc / total
    return out


def delta_summary(loss, arm, reference="M0", blocks=(42, 21, 84), n_boot=2000, seed=7):
    """ΔBrier(arm) = Brier(reference) − Brier(arm). 양수가 개선이다."""
    d = (loss[reference] - loss[arm]).to_numpy()
    fold = loss.index.get_level_values("fold").to_numpy()
    out = {"arm": arm, "reference": reference, "delta": float(d.mean()),
           "by_fold": [float(d[fold == f].mean()) for f in np.unique(fold)]}
    for block in blocks:
        dist = block_bootstrap_mean(d, fold, block, n_boot, seed)
        out[f"ci_low_{block}"], out[f"ci_high_{block}"] = map(float, np.quantile(dist, [0.025, 0.975]))
    return out


def control_table(controls, loss, reference="M0", arm="B"):
    """대조 마스크별 ΔBrier와 군별 순위 p값 (r+1)/(n+1)."""
    ref = float(loss[reference].mean())
    target = ref - float(loss[arm].mean())
    total = controls.groupby("mask")[["sq_sum", "n"]].sum()
    table = pd.DataFrame({"delta": ref - total["sq_sum"] / total["n"]})
    table["group"] = np.where(table.index.str.startswith("Cp"), "Cp", "C")
    p = {}
    for group, g in table.groupby("group"):
        p[group] = float(((g["delta"] >= target).sum() + 1) / (len(g) + 1))
    return table.reset_index(), p


def decide(b, b_minus_w, p):
    """사전 채택안. b는 delta_summary(loss, "B"), b_minus_w는 delta_summary(loss, "B", reference="W")."""
    stage1 = (b["ci_low_42"] > 0
              and sum(v > 0 for v in b["by_fold"]) >= 0.75 * len(b["by_fold"])
              and p.get("C", 1.0) <= 0.05)
    stage2 = bool(stage1 and p.get("Cp", 1.0) <= 0.05 and b_minus_w["ci_low_42"] > 0)
    return {"stage1": bool(stage1), "stage2": stage2}
