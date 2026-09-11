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
    mid-price OHLC candle
    timestamp: candle open time in UTC (as returned by OANDA)
    all prices are mid prices
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

@dataclass(frozen=True)
class Range:
    """
    the 7pm-8pm NY range that defines session levels
    derived from the 1H candle closing at 8pm NY
    """

    high: Decimal
    low: Decimal
    session_date: date  # NY date this range belongs to

    @property
    def r(self) -> Decimal:
        # range size: high - low
        return self.high - self.low

@dataclass(frozen=True)
class EntrySignal:
    """
    output of decide() when a trade should be taken
    notional_entry: the range level that was crossed (range_high or range_low)
    used for stop/target/sizing math, NOT actual fill price
    """

    direction: Direction
    trigger_type: TriggerType
    notional_entry: Decimal
    stop: Decimal
    target: Decimal
    notional_risk_distance: Decimal
    candle_1_position: str  # "above", "below", "inside", "spanning"
    trigger_candle_time: datetime   # candle 3's close time (when to enter)

@dataclass(frozen=True)
class SessionTimes:
    # key timestamps for a trading session, all in UTC
    session_date: date      # NY date identifying this session
    range_start: datetime   # 7pm NY (start of range candle)
    range_end: datetime     # 8pm NY (end of range candle, start of hunt)
    hunt_start: datetime    # same as range_end
    force_close: datetime   # 6:59pm next day, or 3:59pm Fri for Thur