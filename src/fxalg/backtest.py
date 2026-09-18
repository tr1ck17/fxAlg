import csv
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Generator

from .config import CANDLE_DB_PATH, INSTRUMENT, NY
from .types import Candle, Range, EntrySignal, Direction, TriggerType, SessionTimes
from .decision import decide
from .scheduler import get_session_times, next_session_date

@dataclass
class TradeResult:
    # record of a completed backtest trade
    session_date: date
    direction: str
    trigger_type: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    notional_entry: Decimal
    stop: Decimal
    target: Decimal
    notional_risk_distance: Decimal
    range_r: Decimal
    candle_1_position: str
    exit_reason: str    # "target", "stop", "force_close"
    notional_rr: Decimal        # always 2.0 by design
    actual_rr: Decimal          # based on simulated fills

@dataclass
class SessionResult:
    # result of a single session (trade or no trade)
    session_date: date
    had_range: bool
    trade: TradeResult | None
    reason_no_trade: str | None     # "no_setup", "no_range", "no_candles"

def get_candles_for_backtest(
        granularity: str,
        from_time: datetime,
        to_time: datetime,
) -> list[Candle]:
    """
    fetch candles from local storage for backtesting
    imports here to avoid circular dependency
    """
    from .candles import get_candles
    return get_candles(granularity, from_time, to_time, db_path=CANDLE_DB_PATH)

def get_range_for_session(session_date: date) -> Range | None:
    # build a Range object for H1 candle 7-8pm
    times = get_session_times(session_date)
    if times is None:
        return None

    candles = get_candles_for_backtest("H1", times.range_start, times.range_start)

    if not candles:
        return None

    c = candles[0]
    return Range(
        high=c.high,
        low=c.low,
        session_date=session_date,
    )

def simulate_trade_outcome(
        signal: EntrySignal,
        candles_after_entry: list[Candle],
        force_close_time: datetime,
) -> tuple[Decimal, datetime, str]:
    """
    simulate what happens after entry
    walks through candles to determine if stop, target, or force_close hits first
    returns:
        (exit_price, exit_time, exit_reason)
    """
    entry_price = signal.notional_entry         # backtest uses notional as fill

    for candle in candles_after_entry:
        # check if this candle hits stop or target
        if signal.direction == Direction.LONG:
            # stop hit if low <= stop
            if candle.low <= signal.stop:
                return (signal.stop, candle.timestamp, "stop")
            # target hit if high >= target
            if candle.high >= signal.target:
                return (signal.target, candle.timestamp, "target")
        else: #SHORT
            # stop hit if high >= stop
            if candle.high >= signal.stop:
                return (signal.stop, candle.timestamp, "stop")
            # target hit if low <= target
            if candle.low <= signal.target:
                return (signal.target, candle.timestamp, "target")

        # check for force close
        if candle.timestamp >= force_close_time:
            return (candle.close, candle.timestamp, "force_close")

    # if we run out of candles, use last candle's close (incomplete data)
    if candles_after_entry:
        last = candles_after_entry[-1]
        return (last.close, last.timestamp, "force_close")

    # no candles at all after entry - shouldn't happen with good data
    return (entry_price, force_close_time, "force_close")

def compute_actual_rr(
        entry_price: Decimal,
        exit_price: Decimal,
        stop: Decimal,
        direction: Direction,
) -> Decimal:
    """
    compute actual RR based on fill prices
    actual_rr = (exit - entry) / (entry - stop) for long
    actual_rr = (entry - exit) / (stop - entry) for short
    """

    if direction == Direction.LONG:
        risk = entry_price - stop
        if risk == 0:
            return Decimal("0")
        reward = exit_price - entry_price
        return reward / risk
    else:
        risk = stop - entry_price
        if risk == 0:
            return Decimal("0")
        reward = entry_price - exit_price
        return reward / risk

def run_session(session_date: date) -> SessionResult:
    """
    run backtest for a single session
    simulates calling decide() at each 5M candle close
    """
    times = get_session_times(session_date)
    if times is None:
        return SessionResult(
            session_date=session_date,
            had_range=False,
            trade=None,
            reason_no_trade="no_session",
        )

    # get range
    range_ = get_range_for_session(session_date)
    if range_ is None:
        return SessionResult(
            session_date=session_date,
            had_range=False,
            trade=None,
            reason_no_trade="no_range",
        )

    # get all 5M candles for the hunt period
    all_candles = get_candles_for_backtest("M5", times.hunt_start - timedelta(minutes=5), times.force_close)
    if len(all_candles) < 3:
        return SessionResult(
            session_date=session_date,
            had_range=True,
            trade=None,
            reason_no_trade="no_candles",
        )
    # simulate live: call decide() at each candle close
    for i in range(3, len(all_candles) + 1):
        candles_so_far = all_candles[:i]
        signal = decide(candles_so_far, range_)

        if signal is not None:
            # signal fired, simulate trade
            entry_time = signal.trigger_candle_time
            entry_price = signal.notional_entry

            # get candles after entry for outcome simulation
            candles_after = all_candles[i:]

            exit_price, exit_time, exit_reason = simulate_trade_outcome(
                signal, candles_after, times.force_close
            )

            actual_rr = compute_actual_rr(
                entry_price, exit_price, signal.stop, signal.direction
            )

            trade = TradeResult(
                session_date=session_date,
                direction=signal.direction.value,
                trigger_type=signal.trigger_type.value,
                entry_time=entry_time,
                exit_time=exit_time,
                entry_price=entry_price,
                exit_price=exit_price,
                notional_entry=signal.notional_entry,
                stop=signal.stop,
                target=signal.target,
                notional_risk_distance=signal.notional_risk_distance,
                range_r=range_.r,
                candle_1_position=signal.candle_1_position,
                exit_reason=exit_reason,
                notional_rr=Decimal("2.0"), # by design: target = 2R
                actual_rr=actual_rr,
            )

            return SessionResult(
                session_date=session_date,
                had_range=True,
                trade=trade,
                reason_no_trade=None,
            )

        # no signal fired all session
        return SessionResult(
            session_date=session_date,
            had_range=True,
            trade=None,
            reason_no_trade="no_setup",
        )

def iterate_sessions(
        start_date: date,
        end_date: date,
) -> Generator[date, None, None]:
    """
    generate all valid session dates in range
    skips fri and sat
    """
    current = start_date
    while current <= end_date:
        if current.weekday() not in (4, 5):         # skip Fri, Sat
            yield current
        current += timedelta(days=1)

def run_backtest(
        start_date: date,
        end_date: date,
        output_path: Path | None = None,
) -> list[SessionResult]:
    """
    run backtest over date range
    args:
        start_date
        end_date
        output_path: csv of trades here
    returns:
        list of SessionResult for each session
    """
    results = []
    for session_date in iterate_sessions(start_date, end_date):
        result = run_session(session_date)
        results.append(result)

        # progress indicator
        status = "TRADE" if result.trade else result.reason_no_trade
        print(f"{session_date}: {status}")

    if output_path:
        write_trades_csv(results, output_path)

    return results

def write_trades_csv(results: list[SessionResult], output_path: Path) -> None:
    # write trade results to csv
    trades = [r.trade for r in results if r.trade is not None]

    if not trades:
        print("No trades to write.")
        return

    fieldnames = [
        "session_date",
        "direction",
        "trigger_type",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "notional_entry",
        "stop",
        "target",
        "notional_risk_distance",
        "range_r",
        "candle_1_position",
        "exit_reason",
        "notional_rr",
        "actual_rr",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            row = asdict(trade)
            # convert types for CSV
            row["session_date"] = str(row["session_date"])
            row["entry_time"] = row["entry_time"].isoformat()
            row["exit_time"] = row["exit_time"].isoformat()
            row["entry_price"] = str(row["entry_price"])
            row["exit_price"] = str(row["exit_price"])
            row["notional_entry"] = str(row["notional_entry"])
            row["stop"] = str(row["stop"])
            row["target"] = str(row["target"])
            row["notional_risk_distance"] = str(row["notional_risk_distance"])
            row["range_r"] = str(row["range_r"])
            row["notional_rr"] = str(row["notional_rr"])
            row["actual_rr"] = str(round(row["actual_rr"], 4))
            writer.writerow(row)

    print(f"Wrote {len(trades)} trades to {output_path}")

def print_summary(results: list[SessionResult]) -> None:
    # print backtest summary stats
    trades = [r.trade for r in results if r.trade is not None]
    no_setup = sum(1 for r in results if r.trade is not None)
    no_range = sum(1 for r in results if r.reason_no_trade == "no_setup")
    no_candles = sum(1 for r in results if r.reason_no_trade == "no_candles")

    print("\n" + "=" * 50)
    print("BACKTEST SUMMARY")
    print("=" * 50)
    print(f"Total Sessions: {len(results)}")
    print(f"Sessions Traded: {len(trades)}")
    print(f"No Setup:       {no_setup}")
    print(f"No range data:  {no_range}")
    print(f"No candle data: {no_candles}")

    if not trades:
        print("\nNo trades to analyze")
        return

    # win/loss stats
    wins = [t for t in trades if t.actual_rr > 0]
    losses = [t for t in trades if t.actual_rr <= 0]

    print(f"/nWins:             {len(wins)}")
    print(f"Losses:             {len(losses)}")
    print(f"Win rate:           {len(wins) / len(trades) * 100:.1f}%")

    # RR stats
    total_rr = sum(t.actual_rr for t in trades)
    avg_rr = total_rr / len(trades)
    print(f"\nTotal R:      {total_rr:.2f}")
    print(f"Average R:      {avg_rr:.2f}")

    # by exit reason
    targets = [t for t in trades if t.exit_reason == "target"]
    stops = [t for t in trades if t.exit_reason == "stop"]
    force = [t for t in trades if t.exit_reason == "force_close"]

    print(f"\nExit at target:       {len(targets)}")
    print(f"Exit at stop:           {len(stops)}")
    print(f"Exit force close:       {len(force)}")

    # by trigger type
    breakouts = [t for t in trades if t.trigger_type == "breakout"]
    rejections = [t for t in trades if t.trigger_type == "rejection"]

    print(f"\nBreakout trades:      {len(breakouts)}")
    print(f"Rejection trades:       {len(rejections)}")

    # by candle 1 position
    print("\nBy candle 1 position:")
    positions = {}
    for t in trades:
        pos = t.candle_1_position
        if pos not in positions:
            positions[pos] = []
        positions[pos].append(t)

    for pos, pos_trades in sorted(positions.items()):
        pos_wins = sum(1 for t in pos_trades if t.actual_rr > 0)
        print(f"    {pos}: {len(pos_trades)} trades, {pos_wins} wins")

    print("=" * 50)