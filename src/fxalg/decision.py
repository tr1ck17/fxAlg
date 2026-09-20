"""
pure decision function for AUDJPY strategy
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .types import Candle, Range, EntrySignal, Direction, TriggerType

# internal data structures

@dataclass(frozen=True)
class FVG:
    # fvg's detected from 3 consecutive candles
    is_bullish: bool
    candle_1: Candle
    candle_2: Candle    # displacement candle
    candle_3: Candle

@dataclass(frozen=True)
class Excursion:
    # tracks if price has moved beyond range levels
    above_range_high: bool  # at least one candle with open AND close > range_high
    below_range_low: bool   # at least one candle with open AND close < range_low


# helper functions, all pure
def detect_fvg(c1: Candle, c2: Candle, c3: Candle) -> FVG | None:
    """
    bullish fvg: c3.low > c1.high (gap above)
    bearish fvg: c3.high < c1.low (gap below)
    middle candle (c2) is displacement candle
    returns:
        fvg object if gap exists, None otherwise
    """
    # bullish: candle 3 low strictly above candle 1 high
    if c3.low > c1.high:
        return FVG(
            is_bullish=True,
            candle_1=c1,
            candle_2=c2,
            candle_3=c3,
        )

    # bearish: candle 3 high strictly below candle 1 low
    if c3.high < c1.low:
        return FVG(
            is_bullish=False,
            candle_1=c1,
            candle_2=c2,
            candle_3=c3,
        )

    return None

def detect_excursion(candles: Sequence[Candle], range_: Range) -> Excursion:
    """
    scan candles to find early excursion beyond range levels
    excursion req: both open and close strictly beyonf the level, wicks don't count
    args:
        candles: Candles to scan (exclude current FVG candles)
        range_: curr session range
    returns:
        excursion indicates which levels been exceeded
    """
    above = False
    below = False

    for c in candles:
        if c.close > range_.high:
            above = True
        if c.close < range_.low:
            below = True

    return Excursion(above_range_high=above, below_range_low=below)


def classify_candle_position(candle: Candle, range_: Range) -> str:
    """
    classify where candle 1 sits relative to the range
    used for logging to enable future analysis of whether candle 1 position affects win rate
    returns one of:
        "above" - entire candle above range (low > range_high)
        "below" - entire candle below range (high < range_low)
        "inside" - entire candle within range (low >= range_low, high <= range_high)
        "spanning" - candle crosses at least one range boundary
    """
    if candle.low > range_.high:
        return "above"
    if candle.high < range_.low:
        return "below"
    if candle.low >= range_.low and candle.high <= range_.high:
        return "inside"
    return "spanning"

def check_breakout(
        fvg: FVG,
        range_: Range,
) -> EntrySignal | None:
    """
    check if fvg represent breakout trigger
    bullish breakout at range_high:
        - mid.open <= range_high
        - mid.close > range_high
        - fvg is bullish
    bearish breakout at range_low:
        - mid.open >= range_low
        - mid.close < range_low
        - fvg is bearish
    stop: (currently, to be altered later on further study) 0.1R past the OPPOSITE side of range
    target: notional_entry + (2 x 1.1R) in trade direction
    """
    mid = fvg.candle_2  # displacement candle
    r = range_.r

    # bullish breakout above range_high
    if fvg.is_bullish and mid.open <= range_.high and mid.close > range_.high:
        notional_entry = range_.high
        notional_risk = Decimal("1.1") * r
        stop = range_.low - (Decimal("0.1") * r)
        target = notional_entry + (Decimal("2") * notional_risk)

        return EntrySignal(
            direction=Direction.LONG,
            trigger_type=TriggerType.BREAKOUT,
            notional_entry=notional_entry,
            stop=stop,
            target=target,
            notional_risk_distance=notional_risk,
            candle_1_position=classify_candle_position(fvg.candle_1, range_),
            trigger_candle_time=fvg.candle_3.timestamp,
        )

    # bearish breakout below range_low
    if not fvg.is_bullish and mid.open >= range_.low and mid.close < range_.low:
        notional_entry = range_.low
        notional_risk = Decimal("1.1") * r
        stop = range_.high + (Decimal("0.1") * r)
        target = notional_entry - (Decimal("2") * notional_risk)

        return EntrySignal(
            direction=Direction.SHORT,
            trigger_type=TriggerType.BREAKOUT,
            notional_entry=notional_entry,
            stop=stop,
            target=target,
            notional_risk_distance=notional_risk,
            candle_1_position=classify_candle_position(fvg.candle_1, range_),
            trigger_candle_time=fvg.candle_3.timestamp,
        )

    return None

def check_rejection(
        fvg: FVG,
        range_: Range,
        excursion: Excursion,
) -> EntrySignal | None:
    """
    check if fvg represents inward rejection trigger
    requires previous move beyond the level being rejected
    bearish rejection at range_high (after excursion above):
        - prior excursion above range_high
        - mid.open >= range_high
        - mid.close < range_high
        - fvg is bearish (price moving back down)
    bullish rejection at range_low:
        - prior excursion below range_low
        - mid.open <= range_low
        - mid.close > range_low
        - fvg is bullish
    stop: 1.0R past the crossed level, on the far side of the range
    target: notional_entry + (2 x 1.0R) in trade direction
    """
    mid = fvg.candle_2
    r = range_.r

    # bearish rejection
    if (
        excursion.above_range_high
        and not fvg.is_bullish
        and mid.open >= range_.high
        and mid.close < range_.high
    ):
        notional_entry = range_.high
        notional_risk = Decimal("1.0") * r
        stop = range_.high + (Decimal("1.0") * r)
        target = notional_entry - (Decimal("2") * notional_risk)

        return EntrySignal(
            direction=Direction.SHORT,
            trigger_type=TriggerType.REJECTION,
            notional_entry=notional_entry,
            stop=stop,
            target=target,
            notional_risk_distance=notional_risk,
            candle_1_position=classify_candle_position(fvg.candle_1, range_),
            trigger_candle_time=fvg.candle_3.timestamp,
        )

    # bullish rejection
    if (
        excursion.below_range_low
        and fvg.is_bullish
        and mid.open <= range_.low
        and mid.close > range_.low
    ):
        notional_entry = range_.low
        notional_risk = Decimal("1.0") * r
        stop = range_.low - (Decimal("1.0") * r)
        target = notional_entry + (Decimal("2") * notional_risk)

        return EntrySignal(
            direction=Direction.LONG,
            trigger_type=TriggerType.REJECTION,
            notional_entry=notional_entry,
            stop=stop,
            target=target,
            notional_risk_distance=notional_risk,
            candle_1_position=classify_candle_position(fvg.candle_1, range_),
            trigger_candle_time=fvg.candle_3.timestamp,
        )

    return None

# main decision function
def decide(candles_5m: Sequence[Candle], range_: Range) -> EntrySignal | None:
    """
    pure decision function
    called:
        - live: reach time new 5M candle completes
        - recovery: iteratively with growing candle sequences
        - backtest: iteratively simulating live calls
    args:
        candles_5m: completed 5M mid candles from hunt_start to now, chronologically
        range_: session's range
    returns:
        none if no trade signal at this moment
        EntrySignal is the most recent candle completes a qualifying setup
    logic:
        need at least 3 candles for fvg detection
        check if last 3 candles form fvg
        if fvg exists, check for breakout trigger
        if not breakout, check for rejection trigger
        return signal or None
    """

    # 3 candles to form fvg
    if len(candles_5m) < 3:
        return None

    # check most recent 3 candles for fvg
    c1, c2, c3 = candles_5m[-3], candles_5m[-2], candles_5m[-1]
    fvg = detect_fvg(c1, c2, c3)

    if fvg is None:
        return None

    # check for breakout trigger first
    signal = check_breakout(fvg, range_)
    if signal is not None:
        return signal

    # check rejection trigger
    # include c1 of the FVG, it may be the excursion candle (immediate rejection)
    prior_candles = candles_5m[:-2] # everything up to and including c1
    excursion = detect_excursion(prior_candles, range_)

    signal = check_rejection(fvg, range_, excursion)
    if signal is not None:
        return signal

    return None

# design points
# zero I/O - no imports of requests, sqlite3, datetime.now(), just pure transformation of candles in, decision out
# breakout checked first. breakout and rejection CAN both happen, but breakout takes precedence
# excursion excludes FVG candles - breakout cannot be part of the rejection decision
# strict inequalities - c3.low > c1.high
# candle_1_position logged on every signal
# trigger_candle_time candle 3's timestamp