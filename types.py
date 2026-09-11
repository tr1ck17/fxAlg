from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class Direction(Enum):
    LONG = "long"
    SHORT = "short"

class TriggerType(Enum):
    BREAKOUT = "breakout"
    REJECTION = "rejection"

class SessionStatus(Enum):
    WAITING_FOR_RANGE = "waiting_for_range"
    HUNTING = "hunting"
    IN_TRADE = "in_trade"
    SPENT = "spent"
    MANUAL_OVERRIDE = "manual_override"
    CLOSED = "closed"

@dataclass(frozen=True)
class Candle:
    """
    Mid-price OHLC candle
    timestamp: Candle open time in UTC (returned by OANDA)
    All prices are mid prices
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

@dataclass(frozen=True)
class Range:
    """
    The 7pm-8pm NY range that defines session levels
    Derived from the 1H candle closing at 8pm NY
    """

    high: Decimal
    low: Decimal
    session_date: date # NY date this range belongs to

    @property
    def r(self) -> Decimal:
        """Range size: high - low"""
        return self.high - self.low

@dataclass(frozen=True)
class EntrySignal:
    """
    Output of decidce() when a trade should be taken
    notional_entry: the range level that was crossed (range_high or range_low)
        used for stop/target/sizing math, NOT the actual fill price
    """

    direction: Direction
    trigger_type: TriggerType
    notional_entry: Decimal
    stop: Decimal
    target: Decimal
    notional_risk_distance: Decimal
    candle_1_position: str      # "above", "below", "inside", "spanning"
    trigger_candle_time: datetime       # Candle 3's close time (when to enter)


@dataclass(frozen=True)
class SessionTimes:
    """
    Key timestamps for a trading session, all in UTC"""
    session_date: date          # NY date identifying the session
    range_start: datetime       # 7pm NY (start of range candle)
    range_end: datetime         # 8pm NY (end of range candle, start of hunt)
    hunt_start: datetime        # same as range_end
    force_close: datetime       # 6:59pm next day, or 3:59pm Fri for Thursday

    # frozen=True makes these immutable, the candle data should never change after creation
    # Decimal type becayse prices need exact arithmetic, OANDA returns strings, we parse right to Decimal

    