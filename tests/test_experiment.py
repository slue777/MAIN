"""스텀프 분류기 이식, 기준선 특징, 실험·평가 파이프라인 검사."""
import json

import numpy as np
import pandas as pd
import pytest

from mangoldt import evaluate, stump
from mangoldt.data import read_bars, validate_bars
from mangoldt.experiment import Config, M0, build_frame, folds, run
from mangoldt.features import baseline_core, d_rel_many, kernel_features
from mangoldt.kernels import control_kernels, mangoldt_weights, wheel_weights
from mangoldt.run import main

CFG = Config(n_masks=20, seeds=(42, 43), n_trees=100)


def make_bars(n=4000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="4h", tz="UTC", name="time")
    r = np.empty(n)
    v = 1e-4
    for i in range(n):
        r[i] = np.sqrt(v) * rng.standard_normal()
        v = 5e-6 + 0.1 * r[i] ** 2 + 0.85 * v
    close = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
    bars = pd.DataFrame({"open": close.shift().fillna(100.0), "close": close})
    bars["high"] = bars.max(axis=1) * 1.001
    bars["low"] = bars[["open", "close"]].min(axis=1) * 0.999
    bars["volume"] = rng.uniform(1, 2, n)
    return bars[["open", "high", "low", "close", "volume"]]


@pytest.fixture(scope="module")
def bars():
    return make_bars()


@pytest.fixture(scope="module")
def frame(bars):
    return build_frame(bars, CFG)[0]


def pine_reference(X, Y, Xe, seed, n_trees, tries=10):
    """Pine trainClassifier / predictProb를 반복문 그대로 옮긴 참조 구현."""
    s = stump.Sampler(seed)
    ns, nf = X.shape
    p = sum(Y) / ns
    base = 1 - p * p - (1 - p) * (1 - p)
    trees = []
    for _ in range(n_trees):
        f = s.pick(nf)
        best, thr, lp, rp = -1.0, X[0, f], 0.5, 0.5
        for _ in range(tries):
            t = X[s.pick(ns), f]
            lb = lt = rb = rt = 0
            for k in range(ns):
                if X[k, f] <= t:
                    lt += 1
                    lb += Y[k] == 1
                else:
                    rt += 1
                    rb += Y[k] == 1
            if lt > 0 and rt > 0:
                pl, pr = lb / lt, rb / rt
                gain = base - (lt * (1 - pl * pl - (1 - pl) ** 2) + rt * (1 - pr * pr - (1 - pr) ** 2)) / ns
                if gain > best:
                    best, thr, lp, rp = gain, t, pl, pr
        trees.append((f, thr, lp, rp))
    return np.array([sum(l if x[f] <= t else r for f, t, l, r in trees) / n_trees for x in Xe])


def test_sampler_matches_park_miller():
    s = stump.Sampler(42)
    assert s.pick(10 ** 9) == 944073          # 42·48271 = 2027382
    assert s.state == 2027382
    with pytest.raises(ValueError):
        stump.Sampler(0)


def test_stump_port_matches_reference():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, 5))
    X[:, 3] = X[:, 3] > 0          # 지시변수 열
    X[:, 4] = 1.0                  # 분할할 수 없는 열 → 0.5 / 0.5
    Y = (X[:, 0] + rng.normal(size=60) > 0).astype(int)
    Xe = rng.normal(size=(25, 5))
    for seed in (1, 42, 999):
        got = stump.predict_proba(X, Y, Xe, seed, n_trees=30)
        assert got == pytest.approx(pine_reference(X, Y, Xe, seed, 30), abs=1e-12)


def test_stump_rejects_bad_input():
    X = np.ones((5, 2))
    with pytest.raises(ValueError):
        stump.predict_proba(X[:0], [], X, 1)
    X[2, 0] = np.nan
    with pytest.raises(ValueError):
        stump.predict_proba(X, [0, 1, 0, 1, 0], X, 1)


def test_d_rel_many_matches_single_kernel(bars):
    close = bars["close"].drop(bars.index[500])
    w = mangoldt_weights()
    ks = [w, wheel_weights()] + control_kernels(w, 3, 1)
    many = d_rel_many(close, ks)
    for i, k in enumerate(ks):
        one = kernel_features(close, k)["d_rel"]
        assert many[i].isna().equals(one.isna())
        assert np.nanmax(np.abs(many[i] - one)) < 1e-12


def test_baseline_core_is_causal_and_bounded(bars):
    core = baseline_core(bars)
    assert np.allclose(baseline_core(bars.iloc[:900]), core.iloc[:900], equal_nan=True)
    done = core.dropna()
    assert len(done) == len(bars) - 19
    assert (done["atr_rel"] > 0).all() and (done["vol_rel"] > 0).all()
    assert done["vidya_rel"].abs().max() < 1


def test_validate_bars_rejects_inconsistent_rows(bars):
    bad = bars.copy()
    bad.iloc[10, bad.columns.get_loc("high")] = bad["low"].iloc[10] * 0.5
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        validate_bars(bad)
    with pytest.raises(ValueError, match="duplicate"):
        validate_bars(pd.concat([bars.iloc[:5], bars.iloc[4:8]]))
    with pytest.raises(ValueError, match="negative volume"):
        validate_bars(bars.assign(volume=-1.0))


def test_read_bars_roundtrip(bars, tmp_path):
    path = tmp_path / "bars.csv"
    bars.to_csv(path)
    pd.testing.assert_frame_equal(read_bars(path), bars, check_freq=False)
    shifted = bars.copy()
    shifted.index = (shifted.index + pd.Timedelta(hours=4)).as_unit("ms").astype("int64")
    shifted.to_csv(path, index_label="time")
    pd.testing.assert_frame_equal(read_bars(path, index_is_close=True), bars, check_freq=False)
    cut = read_bars(tmp_path / "bars.csv", index_is_close=True, now=bars.index[100])
    assert cut.index[-1] == bars.index[99]


def test_folds_are_purged_and_ordered(frame):
    seen = []
    for k, train, evaluate_rows in folds(frame, CFG):
        start = frame.index[evaluate_rows][0]
        assert (frame["label_end"][train] < start).all()
        assert frame.index[train].max() < start
        assert not (train & evaluate_rows).any()
        seen.append(frame.index[evaluate_rows])
    assert all(a.max() < b.min() for a, b in zip(seen, seen[1:]))
    assert sum(len(s) for s in seen) >= 0.49 * len(frame)


def test_run_outputs_are_aligned(frame):
    predictions, controls = run(frame, CFG)
    counts = predictions.groupby(["arm", "seed"])["time"].count()
    assert counts.nunique() == 1 and len(counts) == 5 * len(CFG.seeds)
    times = [tuple(g["time"]) for _, g in predictions.groupby(["arm", "seed"])]
    assert all(t == times[0] for t in times)
    assert predictions["prob"].between(0, 1).all()
    assert controls["mask"].nunique() == 2 * CFG.n_masks
    assert (controls.groupby("fold")["n"].first().sum()
            == predictions.query("arm == 'M0' and seed == 42").shape[0])
    again, _ = run(frame, CFG)
    pd.testing.assert_frame_equal(predictions, again)


def test_shared_plan_only_changes_the_extra_column(frame):
    """B와 W는 13번째 열만 다르므로, 그 열을 같게 하면 예측이 완전히 같아야 한다."""
    same = frame.assign(W=frame["B"])
    predictions, _ = run(same, CFG)
    wide = predictions.pivot_table(index=["time", "seed"], columns="arm", values="prob")
    assert (wide["B"] == wide["W"]).all()
    assert not (wide["B"] == wide["M0"]).all()


def test_pipeline_detects_a_planted_effect(frame):
    """목표값을 B 열로 직접 만들면 1단계는 통과해야 한다."""
    rng = np.random.default_rng(0)
    planted = frame.copy()
    planted["target"] = (planted["B"] + rng.normal(0, 0.05, len(planted))).where(frame["target"].notna())
    predictions, controls = run(planted, CFG)
    loss = evaluate.paired_loss(predictions)
    b = evaluate.delta_summary(loss, "B", n_boot=300)
    _, p = evaluate.control_table(controls, loss)
    assert b["ci_low_42"] > 0 and all(v > 0 for v in b["by_fold"])
    assert p["C"] == pytest.approx(1 / (CFG.n_masks + 1))
    decision = evaluate.decide(b, evaluate.delta_summary(loss, "B", reference="W", n_boot=300), p)
    assert decision["stage1"]


def test_metrics():
    p = np.array([0.0, 0.25, 0.75, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    assert evaluate.brier(p, y) == pytest.approx(0.03125)
    assert np.isfinite(evaluate.log_loss(p, y))
    assert evaluate.log_loss(p, 1 - y) > 10
    table = evaluate.calibration_table(p, y)
    assert table["n"].tolist() == [1, 0, 1, 0, 0, 0, 0, 1, 0, 1]
    assert evaluate.ece(p, y) == pytest.approx(0.125)


def test_block_bootstrap_is_centred_and_respects_folds():
    rng = np.random.default_rng(1)
    values = np.concatenate([rng.normal(1, 1, 300), rng.normal(-1, 1, 100)])
    fold = np.repeat([0, 1], [300, 100])
    dist = evaluate.block_bootstrap_mean(values, fold, 42, n_boot=500)
    assert dist.mean() == pytest.approx(values.mean(), abs=0.05)
    short = evaluate.block_bootstrap_mean(values[:10], fold[:10], 42, n_boot=50)
    assert np.isfinite(short).all()


def test_decide_thresholds():
    good = {"ci_low_42": 0.001, "by_fold": [1, 1, 1, -1]}
    assert evaluate.decide(good, {"ci_low_42": 0.001}, {"C": 0.01, "Cp": 0.01}) == {"stage1": True, "stage2": True}
    assert evaluate.decide(good, {"ci_low_42": -0.001}, {"C": 0.01, "Cp": 0.01}) == {"stage1": True, "stage2": False}
    assert evaluate.decide(good, {"ci_low_42": 0.001}, {"C": 0.2, "Cp": 0.01}) == {"stage1": False, "stage2": False}
    weak = {"ci_low_42": 0.001, "by_fold": [1, 1, -1, -1]}
    assert not evaluate.decide(weak, {"ci_low_42": 0.001}, {"C": 0.01, "Cp": 0.01})["stage1"]


def test_cli_writes_all_outputs(bars, tmp_path):
    path = tmp_path / "bars.csv"
    bars.to_csv(path)
    out = tmp_path / "out"
    summary = main([str(path), "--out", str(out), "--trees", "30", "--masks", "5"])
    names = {"predictions.csv", "runs.csv", "segments.csv", "calibration.csv",
             "controls.csv", "kernels.csv", "summary.json"}
    assert names <= {p.name for p in out.iterdir()}
    saved = json.loads((out / "summary.json").read_text())
    assert saved["decision"] == summary["decision"]
    assert len(saved["data_sha256"]) == 64 and saved["bars"] == len(bars)
    assert len(pd.read_csv(out / "controls.csv")) == 10
    assert len(M0) == 12
