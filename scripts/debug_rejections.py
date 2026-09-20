# find sesh's with excursions, see why rejections aren't triggering
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fxalg.candles import get_candles, init_db
from src.fxalg.scheduler import get_session_times
from src.fxalg.decision import detect_fvg, detect_excursion
from src.fxalg.types import Range
from src.fxalg.config import CANDLE_DB_PATH

def check_session_for_excursion(session_date: date) -> dict | None:
    # check if a sesh had excursion beyond the range
    times = get_session_times(session_date)
    if times is None:
        return None

    # get range
    range_candles = get_candles("H1", times.range_start, times.range_start, db_path=CANDLE_DB_PATH)
    if not range_candles:
        return None

    rc = range_candles[0]
    range_ = Range(high=rc.high, low=rc.low, session_date=session_date)

    # get 5M candles
    fetch_start = times.hunt_start - timedelta(minutes=5)
    candles = get_candles("M5", fetch_start, times.force_close, db_path=CANDLE_DB_PATH)
    if len(candles) < 3:
        return None

    # check for excursions
    excursion = detect_excursion(candles, range_)

    if excursion.above_range_high or excursion.below_range_low:
        # found excursion, now check if any FVG formed after it
        fvg_count = 0
        bearish_fvg_after_excursion_above = 0
        bullish_fvg_after_excursion_below = 0

        for i in range(len(candles) - 2):
            c1, c2, c3 = candles[i], candles[i+1], candles[i+2]
            fvg = detect_fvg(c1, c2, c3)
            if fvg:
                fvg_count += 1
                # check if could be rejection
                prior = candles[:i]
                prior_excursion = detect_excursion(prior, range_)

                if prior_excursion.above_range_high and not fvg.is_bullish:
                    # potential bearish rejection, check mid candle
                    mid = c2
                    if mid.open >= range_.high and mid.close < range_.high:
                        bearish_fvg_after_excursion_above += 1
                        print(f"    POTENTIAL REJECTION: {session_date}")
                        print(f"    Bearish FVG at candle {i}, mid.open={mid.open}, mid.close={mid.close}")
                        print(f"    range_high={range_.high}")

                if prior_excursion.below_range_low and fvg.is_bullish:
                    mid = c2
                    if mid.open <= range_.low and mid.close > range_.low:
                        bullish_fvg_after_excursion_below += 1
                        print(f"    POTENTIAL REJECTION: {session_date}")
                        print(f"    Bullish FVG at candle {i}, mid.open={mid.open}, mid.close={mid.close}")
                        print(f"    range_low={range_.low}")

        return {
            "date": session_date,
            "above": excursion.above_range_high,
            "below": excursion.below_range_low,
            "range_high": range_.high,
            "range_low": range_.low,
            "fvg_count": fvg_count,
        }

    return None

def main():
    init_db()

    start = date(2024, 1, 1)
    end = date(2024, 1, 31)

    excursion_sessions = []
    current = start

    while current <= end:
        if current.weekday() not in (4, 5): # skip fri/sat
            print(f"Checking {current}...")
            result = check_session_for_excursion(current)
            if result:
                excursion_sessions.append(result)
        current += timedelta(days=1)
        
    print(f"\n\nSessions with excursions: {len(excursion_sessions)}")
    for s in excursion_sessions[:10]:   # first 10
        direction = "ABOVE" if s["above"] else "BELOW"
        print(f"    {s['date']}: {direction} range, {s['fvg_count']} FVGs in session")

if __name__ == "__main__":
    main()