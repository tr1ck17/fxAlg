# script to run backtest
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fxalg.candles import fetch_and_store_candles, init_db
from src.fxalg.backtest import run_backtest, print_summary
from src.fxalg.config import DATA_DIR

def main():
    # init database
    init_db()

    # date range for backtest
    # start with small range to verify working
    start_date = date(2024, 1, 1)
    end_date = date(2024, 6, 30)    # one month

    print(f"Fetching candles from {start_date} to {end_date}...")

    # fetch H1 candles (for range)
    from_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    to_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

    h1_count = fetch_and_store_candles("H1", from_dt, to_dt)
    print(f"Stored {h1_count} H1 candles")

    # fetch M5 candles
    m5_count = fetch_and_store_candles("M5", from_dt, to_dt)
    print(f"Stored {m5_count} M5 candles")

    # run backtest
    print(f"\nRunning backtest from {start_date} to {end_date}...")
    output_path = DATA_DIR / "backtest_results.csv"

    results = run_backtest(start_date, end_date, output_path)
    print_summary(results)

if __name__ == "__main__":
    main()