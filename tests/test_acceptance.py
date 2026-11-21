"""제안서 ⑤-8 구현 수용 검사."""
import numpy as np
import pandas as pd
import pytest

from mangoldt.features import baseline_extras, kernel_features, segment_ids
from mangoldt.kernels import (centroid, control_kernels, mangoldt_weights,
                              residue_shares, wheel_weights)
from mangoldt.labels import binary_label, fit_threshold, forward_rv

W = mangoldt_weights()


def bars(n, seed=0, start="2024-01-01"):
    idx = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    steps = np.random.default_rng(seed).normal(0, 0.01, n)
    return pd.Series(np.exp(np.cumsum(steps)) * 100, index=idx)


def test_kernel_table():
    assert W.sum() == pytest.approx(1)
    assert W[0] == 0
    assert (W > 0).sum() == 27
    assert centroid(W) == pytest.approx(32.01, abs=0.005)
    assert 1 / (W ** 2).sum() == pytest.approx(20.85, abs=0.005)
    assert residue_shares(W) == pytest.approx(
        [0.416, 0.033, 0.053, 0.033, 0.464, 0.0], abs=0.0005)


def test_wheel_table():
    wh = wheel_weights()
    assert wh.sum() == pytest.approx(1)
    assert (wh > 0).sum() == 29
    assert centroid(wh) == pytest.approx(33.55, abs=0.005)
    assert 1 / (wh ** 2).sum() == pytest.approx(23.04, abs=0.005)


@pytest.mark.parametrize("period", [None, 6])
def test_control_kernels(period):
    ks = control_kernels(W, 200, seed=7, period=period)
    assert len({k.tobytes() for k in ks}) == 200
    for k in ks:
        assert k[0] == 0
        assert (k > 0).sum() == 27
        assert (k ** 2).sum() == pytest.approx((W ** 2).sum())
        assert abs(centroid(k) - centroid(W)) <= 0.5
        if period:
            assert residue_shares(k, period) == pytest.approx(residue_shares(W, period))


def test_control_kernels_reports_shortfall():
    with pytest.raises(RuntimeError):
        control_kernels(W, 5, seed=1, tol=0.0, max_tries=50)


def test_constant_abs_return_gives_zero():
    idx = pd.date_range("2024-01-01", periods=200, freq="4h", tz="UTC")
    close = pd.Series(np.exp(np.arange(200) * 0.01), index=idx)
    f = kernel_features(close, W).dropna()
    assert len(f) == 200 - 64
    assert f["d_rel"].abs().max() < 1e-12


def test_flat_price_gives_missing():
    idx = pd.date_range("2024-01-01", periods=200, freq="4h", tz="UTC")
    f = kernel_features(pd.Series(100.0, index=idx), W)
    assert f["d_rel"].isna().all()
    assert (f["diff"].dropna() == 0).all()


def test_unit_impulse_response():
    idx = pd.date_range("2024-01-01", periods=200, freq="4h", tz="UTC")
    logp = np.zeros(200)
    logp[100:] = 1.0  # |r| = 1 at bar 100 only
    f = kernel_features(pd.Series(np.exp(logp), index=idx), W)
    response = f["diff"].to_numpy()[100:164]
    assert response == pytest.approx(W - 1 / 64)


def test_past_features_do_not_change_when_bars_are_added():
    close = bars(400)
    full = kernel_features(close, W)
    part = kernel_features(close[:300], W)
    pd.testing.assert_frame_equal(part, full[:300])
    pd.testing.assert_frame_equal(baseline_extras(close[:300]),
                                  baseline_extras(close)[:300])


def test_windows_do_not_cross_a_gap():
    close = bars(400)
    gapped = close.drop(close.index[200])
    assert segment_ids(gapped.index).nunique() == 2
    f = kernel_features(gapped, W)
    after = f.loc[close.index[201]:]
    assert after["d_rel"].iloc[:64].isna().all()
    assert after["d_rel"].iloc[64:].notna().all()
    alone = kernel_features(close[201:], W)
    pd.testing.assert_frame_equal(after, alone, check_freq=False)
    rv = forward_rv(gapped)
    assert rv.loc[:close.index[199]].iloc[-6:].isna().all()
    e = baseline_extras(gapped)
    assert np.isnan(e.loc[close.index[201], "rv1"])


def test_labels():
    close = bars(300)
    rv = forward_rv(close)
    assert rv.iloc[-6:].isna().all() and rv.iloc[:-6].iloc[1:].notna().all()
    r2 = np.log(close).diff() ** 2
    assert rv.iloc[10] == pytest.approx(r2.iloc[11:17].sum())
    q = fit_threshold(rv[:200])
    label = binary_label(rv, q)
    assert label.iloc[-6:].isna().all()
    assert label[:200].mean() == pytest.approx(0.25, abs=0.01)
    with pytest.raises(ValueError):
        fit_threshold(rv.iloc[-6:])


def test_slot():
    close = bars(12)
    assert baseline_extras(close)["slot"].tolist() == [0, 1, 2, 3, 4, 5] * 2
    by_close = close.copy()
    by_close.index = close.index + pd.Timedelta(hours=4)
    assert baseline_extras(by_close, index_is_close=True)["slot"].tolist() == [0, 1, 2, 3, 4, 5] * 2


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_positive_close_is_rejected(bad):
    close = bars(100)
    close.iloc[50] = bad
    for func in (lambda c: kernel_features(c, W), baseline_extras, forward_rv):
        with pytest.raises(ValueError):
            func(close)


def test_empty_close_is_rejected():
    with pytest.raises(ValueError):
        kernel_features(bars(10)[:0], W)


def test_missing_close_blanks_only_its_windows():
    close = bars(300)
    close.iloc[100] = np.nan
    f = kernel_features(close, W)
    assert f["d_rel"].iloc[100:165].isna().all()
    assert f["d_rel"].iloc[165:].notna().all()
    assert f["d_rel"].iloc[64:100].notna().all()
