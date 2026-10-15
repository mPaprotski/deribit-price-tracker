"""Exercise Beat -> broker -> worker -> mock exchange -> PostgreSQL -> HTTP API."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import urlopen

base = f"http://127.0.0.1:{os.environ.get('WEB_PORT', '18000')}"


def read(path):
    with urlopen(base + path, timeout=5) as response:
        assert response.status == 200
        return json.load(response)


assert read("/health") == {"status": "ok"}
with urlopen(base + "/docs", timeout=5) as response:
    assert response.status == 200
for path in ("/prices", "/prices/filter?ticker=BTC_USD&start_time=200&end_time=100"):
    try:
        read(path)
    except HTTPError as exc:
        assert exc.code == 422
    else:
        raise AssertionError("Expected HTTP 422")

deadline = time.monotonic() + 45
while True:
    histories = {ticker: read(f"/prices?ticker={ticker}") for ticker in ("BTC_USD", "ETH_USD")}
    if all(histories.values()):
        break
    if time.monotonic() >= deadline:
        raise AssertionError("Beat did not collect both prices")
    time.sleep(1)
for ticker, price in (("BTC_USD", "65000.12"), ("ETH_USD", "3000.34")):
    latest = read(f"/prices/latest?ticker={ticker}")
    assert latest["ticker"] == ticker and latest["price"] == price
    timestamp = latest["timestamp"]
    filtered = read(f"/prices/filter?ticker={ticker}&start_time={timestamp}&end_time={timestamp}")
    assert any(row["id"] == latest["id"] for row in filtered)
print("PASS: Compose, Beat, worker, mocked Deribit, PostgreSQL, and all API endpoints")
