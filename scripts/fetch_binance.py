"""바이낸스 공개 보관소에서 BTCUSDT 무기한 선물 4시간봉을 받는다.

사용: python scripts/fetch_binance.py <zip 저장 폴더> <출력 CSV>
"""
import io, sys, zipfile, urllib.request, datetime as dt
import pandas as pd
out_dir, csv_out = sys.argv[1], sys.argv[2]
BASE = "https://data.binance.vision/data/futures/um"
def get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            last = e
        except Exception as e: last = e
    raise last
def parse(blob):
    z = zipfile.ZipFile(io.BytesIO(blob)); raw = z.read(z.namelist()[0]).decode()
    hdr = 0 if raw[:9] == "open_time" else None
    df = pd.read_csv(io.StringIO(raw), header=hdr)
    df = df.iloc[:, :6]; df.columns = ["time", "open", "high", "low", "close", "volume"]; return df
parts, missing = [], []
today = dt.datetime.now(dt.timezone.utc).date(); y, m = 2019, 9
while (y, m) < (today.year, today.month):
    name = f"BTCUSDT-4h-{y}-{m:02d}"
    blob = get(f"{BASE}/monthly/klines/BTCUSDT/4h/{name}.zip")
    if blob is None: missing.append(name)
    else:
        open(f"{out_dir}/{name}.zip", "wb").write(blob); parts.append(parse(blob))
    m += 1
    if m == 13: y, m = y + 1, 1
d = dt.date(today.year, today.month, 1)
while d < today:
    name = f"BTCUSDT-4h-{d.isoformat()}"
    blob = get(f"{BASE}/daily/klines/BTCUSDT/4h/{name}.zip")
    if blob is None: missing.append(name)
    else: parts.append(parse(blob))
    d += dt.timedelta(days=1)
df = pd.concat(parts, ignore_index=True).drop_duplicates("time").sort_values("time")
df.to_csv(csv_out, index=False)
print("rows", len(df), "missing files", missing)
t = pd.to_datetime(df["time"], unit="ms", utc=True); print(t.iloc[0], t.iloc[-1])
gaps = t.diff().dropna(); print("gaps:", (gaps != pd.Timedelta(hours=4)).sum()); print(t[1:][(gaps != pd.Timedelta(hours=4)).to_numpy()].tolist()[:10])
