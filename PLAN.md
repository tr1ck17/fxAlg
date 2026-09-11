# AUDJPY Automated Execution App - Implementation Plan

## Open Decisions

### 1. Language and Stack: Python 3.11+

**Recommendation:** Python with minimal dependencies.

**Reasoning:**
- OANDA v20 API is well-documented for Python; direct `requests` calls are cleaner than wrapper libraries
- `zoneinfo` is in stdlib (3.9+) for proper America/New_York handling—no pytz needed
- `decimal.Decimal` in stdlib for precise price arithmetic
- `dataclasses` for clear, inspectable data structures
- You want to understand every line; Python's explicitness serves that
- Backtest logic is naturally expressed with Python's data structures
- Single-threaded event loop is sufficient (no async complexity needed for polling)

**Dependencies (minimal):**
```
requests>=2.31.0    # HTTP client for OANDA API
python-dotenv       # Load .env credentials
```

No pandas, no numpy, no trading frameworks. The logic is clear enough without them.

---

### 2. Candle Storage: SQLite

**Recommendation:** Single SQLite database file.

**Reasoning:**
- stdlib `sqlite3` module—no dependencies
- Natural fit for "give me 5M candles between X and Y" queries
- Single file, portable, inspectable with any SQLite browser
- Atomic writes prevent corruption on crash
- Easy to identify gaps: "what's the latest candle I have before this timestamp?"

**Schema:**
```sql
CREATE TABLE candles (
    instrument TEXT NOT NULL,
    granularity TEXT NOT NULL,      -- 'H1' or 'M5'
    timestamp_utc TEXT NOT NULL,    -- ISO8601, candle open time
    open TEXT NOT NULL,             -- Stored as string to preserve precision
    high TEXT NOT NULL,
    low TEXT NOT NULL,
    close TEXT NOT NULL,
    complete INTEGER NOT NULL,      -- 1 if candle is complete
    PRIMARY KEY (instrument, granularity, timestamp_utc)
);

CREATE INDEX idx_candles_time ON candles(instrument, granularity, timestamp_utc);
```

Prices stored as TEXT to avoid float precision issues. Converted to `Decimal` on read.

---

### 3. Alerting: Telegram Bot + Log File

**Recommendation:** Telegram bot for push notifications, structured log file as fallback.

**Reasoning:**
- Telegram bot API is one HTTP POST, no SDK needed
- Free, immediate mobile push notifications
- Bot token + chat ID stored in `.env`
- Log file (`logs/fxalg.log`) with structured entries for all events
- Force-close failures and override detections trigger Telegram alert

**Alert-worthy events:**
- Force-close rejected (retry loop active)
- Manual override detected
- Trade entry (informational)
- Trade exit (informational)
- App startup/shutdown

**Implementation:** Simple function that POSTs to `https://api.telegram.org/bot{token}/sendMessage`.

---

## Module Layout

```
fxAlg/
├── src/
│   └── fxalg/
│       ├── __init__.py
│       ├── config.py           # Settings, credentials, constants
│       ├── types.py            # All dataclasses and enums
│       ├── candles.py          # OANDA candle fetching + SQLite storage
│       ├── decision.py         # THE pure decision function
│       ├── backtest.py         # Backtest harness
│       ├── execution.py        # Order submission, fill handling (Step 4)
│       ├── position.py         # Position tracking, override detection (Step 4)
│       ├── scheduler.py        # Session timing, NY timezone logic
│       ├── alerts.py           # Telegram + logging
│       └── main.py             # Entry point, main loop (Step 4)
├── tests/
│   ├── __init__.py
│   ├── test_decision.py        # Unit tests for decision function
│   ├── test_scheduler.py       # Timezone and session boundary tests
│   ├── test_candles.py         # Storage round-trip tests
│   └── fixtures/               # Hand-crafted candle sequences
│       └── breakout_long.json
├── data/                       # Created at runtime, gitignored
│   └── candles.db
├── logs/                       # Created at runtime, gitignored
│   └── fxalg.log
├── .env                        # Credentials, gitignored
├── .env.example                # Template
├── .gitignore
├── requirements.txt
└── pyproject.toml              # Or setup.py, for installable package
```

---

## Data Structures (`types.py`)

```python
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
    """Mid-price OHLC candle. Timestamp is candle open time in UTC."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

@dataclass(frozen=True)
class Range:
    """The 7pm-8pm 1H candle that defines the session's levels."""
    high: Decimal
    low: Decimal
    session_date: date  # NY date this range belongs to

    @property
    def r(self) -> Decimal:
        return self.high - self.low

@dataclass(frozen=True)
class EntrySignal:
    """Output of decide() when a trade should be taken."""
    direction: Direction
    trigger_type: TriggerType
    notional_entry: Decimal       # The crossed level (range_high or range_low)
    stop: Decimal
    target: Decimal
    notional_risk_distance: Decimal
    candle_1_position: str        # "above", "below", "inside", "spanning"
    trigger_candle_time: datetime # Candle 3's timestamp (entry time)

@dataclass(frozen=True)
class SessionTimes:
    """Key timestamps for a trading session."""
    session_date: date
    range_start: datetime   # 7pm NY
    range_end: datetime     # 8pm NY
    hunt_start: datetime    # 8pm NY
    force_close: datetime   # 6:59pm next day (or 3:59pm Fri for Thu)

@dataclass
class SessionState:
    """Mutable state for the current session."""
    session_date: date
    status: SessionStatus
    times: SessionTimes
    range_: Range | None
    candles_5m: list[Candle]
    position: "Position | None"
    trade_result: "TradeResult | None"
    manual_override: bool
    override_reason: str | None

@dataclass
class Position:
    """An open position the app is managing."""
    direction: Direction
    units: int                      # Signed: + long, - short
    entry_fill_price: Decimal
    entry_time: datetime
    client_trade_id: str            # App-generated ID
    stop_order_id: str | None
    target_order_id: str | None
    notional_entry: Decimal
    notional_risk_distance: Decimal
    actual_dollar_risk: Decimal

@dataclass(frozen=True)
class TradeResult:
    """Record of a completed trade for logging/backtest output."""
    session_date: date
    direction: Direction
    trigger_type: TriggerType
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    units: int
    notional_entry: Decimal
    stop: Decimal
    target: Decimal
    notional_risk_distance: Decimal
    actual_dollar_risk: Decimal
    pnl_account_currency: Decimal
    notional_rr: Decimal            # Based on signal levels
    actual_rr: Decimal              # Based on fills
    range_r: Decimal
    candle_1_position: str
    exit_reason: str                # "target", "stop", "force_close", "manual"
```

---

## Decision Function (`decision.py`)

### Signature

```python
from decimal import Decimal
from typing import Sequence
from .types import Candle, Range, EntrySignal

def decide(candles_5m: Sequence[Candle], range_: Range) -> EntrySignal | None:
    """
    Pure decision function. No I/O, no side effects, no clock reads.

    Analyzes the 5M candle sequence to determine if a trade signal
    exists at the current moment (i.e., at the close of the last candle).

    Args:
        candles_5m: Completed 5M mid candles from hunt_start (8pm) to now,
                    in chronological order. Must have at least 3 candles
                    for FVG detection.
        range_: The session's range (from 7pm-8pm 1H candle).

    Returns:
        None if no trade signal at this moment.
        EntrySignal if the most recent candle completes a qualifying setup.

    Assumptions stated for backtest/live comparison:
        - All candles are MID prices
        - Live fills occur at ask (long) or bid (short)
        - Live results will trail backtest by approximately the spread
    """
```

### Return Type

Returns `EntrySignal | None`. The caller is responsible for:
- Not calling if a trade was already taken this session
- Marking session SPENT if signal fires during recovery replay
- Executing the signal if live

### Internal Logic Outline

```python
def decide(candles_5m: Sequence[Candle], range_: Range) -> EntrySignal | None:
    if len(candles_5m) < 3:
        return None

    # Check if last 3 candles form an FVG
    c1, c2, c3 = candles_5m[-3], candles_5m[-2], candles_5m[-1]
    fvg = detect_fvg(c1, c2, c3)

    if fvg is None:
        return None

    # Check for breakout trigger
    signal = check_breakout(c2, range_, fvg)
    if signal:
        return signal

    # Check for rejection trigger (requires prior excursion)
    excursion = detect_excursion(candles_5m[:-2], range_)  # All candles before the FVG
    signal = check_rejection(c2, range_, fvg, excursion)
    if signal:
        return signal

    return None
```

Helper functions (all pure):
- `detect_fvg(c1, c2, c3) -> FVGInfo | None` — checks gap between c1 and c3
- `check_breakout(mid_candle, range_, fvg) -> EntrySignal | None`
- `detect_excursion(candles, range_) -> ExcursionInfo` — scans for prior excursion
- `check_rejection(mid_candle, range_, fvg, excursion) -> EntrySignal | None`
- `classify_candle_position(candle, range_) -> str` — "above", "below", "inside", "spanning"

---

## Session Scheduler (`scheduler.py`)

### Timezone Handling

```python
from zoneinfo import ZoneInfo
from datetime import datetime, date, time, timedelta

NY = ZoneInfo("America/New_York")

# All internal timestamps are UTC (from OANDA)
# Convert to NY only for session boundary logic
# Convert back to UTC for OANDA API calls
```

### Key Functions

```python
def get_session_times(session_date: date) -> SessionTimes | None:
    """
    Given a session date (NY), return all key times for that session.
    Returns None if no session on that date (Friday).

    Session ownership:
    - A session starts at 7pm NY on session_date
    - It ends at force_close time the next day

    Special cases:
    - Friday (weekday=4): No session, return None
    - Thursday (weekday=3): Force close is 3:59pm Friday, not 6:59pm
    - Saturday (weekday=5): No session (market closed)
    - Sunday (weekday=6): Normal session (range at 7pm, 2h after 5pm open)
    """

def get_current_session(now_utc: datetime) -> SessionTimes | None:
    """
    Given current UTC time, determine which session (if any) is active.

    Returns None if:
    - Market is closed (Sat, or Sun before 5pm NY, or Fri after 5pm NY)
    - Between sessions (e.g., 7pm Fri - 5pm Sun)
    - In the gap after Thursday's force close (3:59pm - 5pm Fri)
    """

def is_in_hunt_window(now_utc: datetime, session: SessionTimes) -> bool:
    """True if now is between hunt_start and force_close."""

def next_range_time(now_utc: datetime) -> datetime:
    """
    Returns the next 7pm NY range start time.
    Used for scheduling the next session start.
    Skips Friday and Saturday.
    """
```

### Week Edge Cases

| Current Time (NY) | Session |
|-------------------|---------|
| Sat all day | None |
| Sun before 5pm | None (market closed) |
| Sun 5pm - 6:59pm | None (market open, waiting for range) |
| Sun 7pm - 7:59pm | Sunday session, WAITING_FOR_RANGE (building range candle) |
| Sun 8pm onwards | Sunday session, HUNTING |
| Mon 12am - 6:58pm | Sunday session, HUNTING |
| Mon 6:59pm | Sunday session, force close |
| Mon 7pm onwards | Monday session |
| ... | ... |
| Thu 7pm onwards | Thursday session |
| Fri 12am - 3:58pm | Thursday session, HUNTING |
| Fri 3:59pm | Thursday session, force close |
| Fri 4pm - 5pm | None (gap before close) |
| Fri 5pm onwards | None (market closed) |

---

## Candle Alignment

OANDA's `alignmentTimezone` parameter for candle requests:
- Set to `America/New_York`
- Set `dailyAlignment` to `17` (5pm NY for daily candles, which propagates to hourly alignment)

This ensures the 7pm-8pm hourly candle is exactly 7:00pm to 7:59:59pm NY.

For 5M candles, alignment doesn't affect them (they're always on :00, :05, :10, etc.), but we still set the timezone parameter for consistency.

---

## Test Strategy for Decision Function

### 1. Unit Tests with Fixtures

Create JSON fixtures with hand-crafted candle sequences:

```
tests/fixtures/
├── breakout_long_valid.json       # Should trigger long breakout
├── breakout_short_valid.json      # Should trigger short breakout
├── rejection_long_valid.json      # Should trigger long rejection
├── rejection_short_valid.json     # Should trigger short rejection
├── no_fvg.json                    # No FVG formed
├── fvg_no_breakout.json           # FVG but no level crossed
├── fvg_touching.json              # C1 and C3 exactly touch (no gap)
├── breakout_wrong_direction.json  # FVG direction doesn't match break
├── rejection_no_excursion.json    # Rejection pattern but no prior excursion
└── multiple_fvgs.json             # Verify only first triggers
```

### 2. Edge Case Tests

```python
def test_breakout_open_equals_range():
    """mid.open == range_high exactly, mid.close > range_high → valid"""

def test_breakout_close_equals_range():
    """mid.close == range_high exactly → NOT a break (must be strictly greater)"""

def test_rejection_close_equals_range():
    """mid.close == range_high exactly → NOT a rejection (must be strictly less)"""

def test_fvg_candles_exactly_touching():
    """c3.low == c1.high → NOT an FVG (no gap)"""

def test_excursion_requires_both_open_and_close():
    """Wick beyond level doesn't count as excursion"""
```

### 3. Math Verification Tests

```python
def test_breakout_stop_calculation():
    """Verify stop = range_low - 0.1R for long breakout"""

def test_breakout_target_calculation():
    """Verify target = notional_entry + 2 * 1.1R"""

def test_rejection_stop_calculation():
    """Verify stop = range_high + 1.0R for short rejection"""

def test_rejection_target_calculation():
    """Verify target = notional_entry - 2 * 1.0R for short"""
```

### 4. Property Tests

```python
def test_pure_function():
    """Same inputs always produce same output"""

def test_signal_has_valid_fvg():
    """If signal returned, last 3 candles must form valid FVG"""

def test_candle_1_position_logged():
    """Every signal includes candle_1_position"""
```

### 5. Regression Tests (after backtest)

Capture real historical setups that triggered, store as fixtures, ensure they continue to trigger correctly as code evolves.

---

## Backtest Harness (`backtest.py`)

### Interface

```python
def run_backtest(
    start_date: date,
    end_date: date,
    candle_db_path: Path,
) -> list[TradeResult]:
    """
    Run backtest over historical data.

    For each session date in range:
    1. Load the 7pm-8pm 1H candle as range
    2. Load all 5M candles from 8pm to 6:59pm (or 3:59pm Fri)
    3. Simulate calling decide() at each candle close
    4. If signal fires, record as trade with simulated fill at mid price
    5. Simulate exit at stop, target, or force close

    Returns list of TradeResult for analysis.
    """
```

### Output Fields (per trade)

| Field | Description |
|-------|-------------|
| session_date | NY date of the session |
| direction | LONG or SHORT |
| trigger_type | BREAKOUT or REJECTION |
| notional_rr | Target distance / risk distance from signal |
| actual_rr | (exit - entry) / (entry - stop), signed |
| actual_dollar_risk | Would be computed from sizing in live |
| range_r | Size of the range in pips |
| candle_1_position | Where candle 1 sat relative to range |
| exit_reason | target, stop, or force_close |
| entry_time | Candle 3 close time |
| exit_time | When exit occurred |

### Output Format

CSV file with one row per trade, plus summary statistics:
- Total trades
- Win rate
- Average RR
- Expectancy
- Breakdown by trigger type
- Breakdown by candle_1_position (for future analysis)

---

## Build Order (Detailed)

### Step 1: Candle Fetching and Storage

Files: `config.py`, `types.py`, `candles.py`

Tasks:
1. Define Candle dataclass
2. Create SQLite schema and connection helpers
3. Implement OANDA candle fetch with proper parameters:
   - `alignmentTimezone=America/New_York`
   - `dailyAlignment=17`
   - `granularity=H1` or `M5`
   - `price=M` (mid)
4. Implement "fetch and store" that identifies gaps and fills them
5. Implement query functions: get_range_candle(session_date), get_5m_candles(start, end)

No OANDA writes. Read-only against practice account.

### Step 2: Decision Function

Files: `decision.py`

Tasks:
1. Implement detect_fvg()
2. Implement check_breakout()
3. Implement detect_excursion()
4. Implement check_rejection()
5. Implement decide()
6. Write comprehensive unit tests

No I/O. Pure logic only.

### Step 3: Backtest Harness

Files: `backtest.py`, `scheduler.py`

Tasks:
1. Implement session time calculations
2. Implement backtest loop
3. Generate trade log CSV
4. Generate summary statistics
5. Validate against manual spot-checks of historical data

No OANDA writes. Uses stored candles.

### Step 4: Live Execution (WAIT FOR APPROVAL)

Files: `execution.py`, `position.py`, `alerts.py`, `main.py`

Tasks:
1. Order submission with client extension IDs
2. Position tracking
3. Override detection
4. Force close logic with retry
5. Recovery replay
6. Alerting
7. Main loop and scheduling

This step makes OANDA write calls. Practice account only.

---

## Verification Plan

### Step 1 Verification
- Fetch candles, query them back, verify round-trip
- Spot-check a few candles against OANDA web UI
- Verify timezone alignment: 7pm NY candle starts at correct UTC time

### Step 2 Verification
- All unit tests pass
- Manual walkthrough of a known setup from historical data

### Step 3 Verification
- Run backtest on 1 month of data
- Manually verify 3-5 trades against charts
- Confirm output fields are populated correctly

### Step 4 Verification
- Deploy on practice account
- Monitor for one full session
- Verify order submission, SL/TP placement
- Test override detection by manually modifying position
- Test force close by letting a position run to 6:59pm

---

## Questions Before Proceeding

None from me—the specification is clear. The three open items have been addressed above with recommendations.

Ready to begin Step 1 on your approval.
