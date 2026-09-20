# fetching candles from OANDA and storing locally
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fxalg.candles import fetch_and_store_candles

# date range to fetch
FROM_DATE = datetime(2025, 1, 1, 0, 0, 0)
TO_DATE = datetime(2026, 9, 19, 23, 59, 0)

print(f"Fetching H1 candles from {FROM_DATE} to {TO_DATE}...")
h1_count = fetch_and_store_candles("H1", FROM_DATE, TO_DATE)
print(f"Stored {h1_count} H1 candles")

print(f"\nFetching M5 candles from {FROM_DATE} to {TO_DATE}...")
m5_count = fetch_and_store_candles("M5", FROM_DATE, TO_DATE)
print(f"Stored {m5_count} M5 candles")

print("\nDone!")