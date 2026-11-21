# MAIN

BTC 4시간봉 변동성 예측용 폰 망골트 필터 연구.

- `docs/BTC_4H_Mangoldt_Filter_Design_v1.1.md` — 설계 제안서
- `mangoldt/` — 제안서 구현
  - `data.py` 봉 읽기·검증, `kernels.py` 커널, `features.py` 특징, `labels.py` 라벨
  - `stump.py` RF형 스텀프 분류기 (Pine "GainzAlgo | Rust Stump"의 분류기를 옮긴 것)
  - `experiment.py` 비교 실험, `evaluate.py` 평가·판정, `run.py` 실행
- `tests/` — 수용 검사 (`python -m pytest`)
- `pine/` — TradingView 지표 (D̃ 패널, 가격 결합 약수 엔진 이동평균)

## 실행

```bash
python -m mangoldt.run bars.csv --out out
```

`bars.csv`는 `time, open, high, low, close, volume` 열을 가진 4시간봉이다.
`time`은 UTC 봉 시작 시각이며, 마감 시각이면 `--close-time`을 붙인다.
128봉 민감도 분석은 `--n 128`이다. 판정은 `out/summary.json`에 기록된다.

실제 시장 데이터로는 아직 실행하지 않았다.
Pine 스크립트는 TradingView에서 컴파일을 확인하지 않았다.
