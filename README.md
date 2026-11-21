# MAIN

BTC 4시간봉 변동성 예측용 폰 망골트 필터 연구.

- `docs/BTC_4H_Mangoldt_Filter_Design_v1.1.md` — 설계 제안서
- `mangoldt/` — 커널(`kernels.py`), 특징(`features.py`), 라벨(`labels.py`)
- `tests/` — 제안서 ⑤-8의 구현 수용 검사 (`python -m pytest`)
- `pine/Mangoldt_D_Panel.pine` — D̃ 패널 지표 (TradingView)
- `pine/PrimeAlgo_MA_v3_1.pine` — 가격 결합 약수 엔진 이동평균 (TradingView)

제안서의 data·experiment·evaluate 모듈은 아직 구현하지 않았다.
Pine 스크립트는 TradingView에서 컴파일을 확인하지 않았다.
