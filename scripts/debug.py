# debug single session to see what code detects
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fxalg.candles import get_candles
from src.fxalg.scheduler import get_session_times
from src.fxalg.decision import decide, detect_fvg
from src.fxalg.types import Range
from src.fxalg.config import CANDLE_DB_PATH

def debug_session(session_date: date):
    times = get_session_times(session_date)
    print(f"Session: {session_date}")
    print(f"Range start (UTC): {times.range_start}")
    print(f"Hunt start (UTC): {times.hunt_start}")
    print(f"Force close (UTC): {times.force_close}")
    print()

    # get range candle
    range_candles = get_candles("H1", times.range_start, times.range_start, db_path=CANDLE_DB_PATH)
    if not range_candles:
        print("NO RANGE CANDLE FOUND")
        return

    rc = range_candles[0]
    print(f"Range candle: O={rc.open} H={rc.high} L={rc.low} C={rc.close}")
    range_ = Range(high=rc.high, low=rc.low, session_date=session_date)
    print(f"Range: {range_.low} - {range_.high} (R={range_.r})")
    print()

    # get 5M candles (including 7:55pm)
    fetch_start = times.hunt_start - timedelta(minutes=5)
    candles = get_candles("M5", fetch_start, times.force_close, db_path=CANDLE_DB_PATH)

    print(f"5M candles fetched: {len(candles)}")
    print("First 10 candles:")
    for i, c in enumerate(candles[:10]):
        print(f"    {i}: {c.timestamp} O={c.open} H={c.high} L={c.low} C={c.close}")
    print()

    # check for FVGs in first 10 candles
    print("Checking for FVGs in first 10 candles:")
    for i in range(len(candles[:10]) - 2):
        c1, c2, c3 = candles[i], candles[i+1], candles[i+2]
        fvg = detect_fvg(c1, c2, c3)
        if fvg:
            print(f"    FVG at index {i}-{i+2}: {'BULLISH' if fvg.is_bullish else 'BEARISH'}")
            print(f"    c1.high={c1.high}, c3.low{c3.low} (gap={c3.low - c1.high})")

    # run decide iteratively
    print()
    print("Running decide() on growing candle sequences:")
    for i in range(3, min(50, len(candles) + 1)):
        signal = decide(candles[:i], range_)
        if signal:
            print(f"    SIGNAL at candle {i}: {signal.direction.value} {signal.trigger_type.value}")
            print(f"    Entry: {signal.notional_entry}, Stop: {signal.stop}, Target: {signal.target}")
            break
        elif i in [38, 39, 40, 41]: # around where debug_rejections found something
            print(f"    Candle {i}: no signal")
    else:
        print(" No signal in first 15 candles")

if __name__ == "__main__":
    debug_session(date(2024, 1, 2))