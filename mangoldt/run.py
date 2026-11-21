"""실험 실행: python -m mangoldt.run bars.csv --out out/"""
import argparse
import json

import pandas as pd
from pathlib import Path

from . import evaluate
from .data import data_hash, read_bars
from .experiment import Config, build_frame, run


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="time, open, high, low, close, volume 열을 가진 4시간봉 CSV")
    ap.add_argument("--out", default="out")
    ap.add_argument("--close-time", action="store_true", help="time 열이 봉 마감 시각이면 지정")
    ap.add_argument("--n", type=int, default=64, help="커널 길이 (민감도 분석은 128)")
    ap.add_argument("--trees", type=int, default=300)
    ap.add_argument("--masks", type=int, default=200)
    args = ap.parse_args(argv)

    cfg = Config(n=args.n, n_trees=args.trees, n_masks=args.masks)
    bars = read_bars(args.csv, index_is_close=args.close_time)
    frame, kernels = build_frame(bars, cfg)
    predictions, controls = run(frame, cfg)

    loss = evaluate.paired_loss(predictions)
    runs = evaluate.run_metrics(predictions)
    b = evaluate.delta_summary(loss, "B")
    b_minus_w = evaluate.delta_summary(loss, "B", reference="W")
    ctrl, p = evaluate.control_table(controls, loss)
    summary = {
        "decision": evaluate.decide(b, b_minus_w, p),
        "delta_B": b, "delta_W": evaluate.delta_summary(loss, "W"),
        "delta_B_minus_W": b_minus_w,
        "aux_SD_vs_S": evaluate.delta_summary(loss, "SD", reference="S"),
        "rank_p": p, "config": cfg.record(), "data_sha256": data_hash(bars),
        "first_bar": str(bars.index[0]), "last_bar": str(bars.index[-1]), "bars": len(bars),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(out / "predictions.csv", index=False)
    runs.to_csv(out / "runs.csv", index=False)
    runs.groupby(["fold", "arm"]).mean(numeric_only=True).drop(columns="seed").to_csv(out / "segments.csv")
    mean_prob = predictions.groupby(["time", "arm"])[["prob", "label"]].mean().reset_index()
    cal = [evaluate.calibration_table(g["prob"].to_numpy(), g["label"].to_numpy()).assign(arm=arm)
           for arm, g in mean_prob.groupby("arm")]
    pd.concat(cal).to_csv(out / "calibration.csv", index=False)
    ctrl.to_csv(out / "controls.csv", index=False)
    kernels.to_csv(out / "kernels.csv")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({k: summary[k] for k in ("decision", "rank_p")}, ensure_ascii=False))
    print("ΔBrier(B) =", b["delta"], "95% 구간", (b["ci_low_42"], b["ci_high_42"]))
    return summary


if __name__ == "__main__":
    main()
