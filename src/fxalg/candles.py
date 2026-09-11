"""
Candle fetching from OANDA and local sqlite storage
all timestamps stored and returned in UTC
OANDA's alignment timezone parameter ensures candles align to NY hours
"""

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Sequence
import requests

from .config import(
    OANDA_ACCOUNT_ID,
    OANDA_API_TOKEN,
    OANDA_API_URL,
    INSTRUMENT,
    CANDLE_DB_PATH,
    NY,
)
from .types import Candle

# SQLite setup
def init_db(db_path: Path = CANDLE_DB_PATH) -> None:
    # create the candles table if it doesn't exist
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candles(
                instrument TEXT NOT NULL,
                granularity TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                open TEXT NOT NULL,
                high TEXT NOT NULL,
                low TEXT NOT NULL,
                close TEXT NOT NULL,
                complete INTEGER NOT NULL,
                PRIMARY KEY (instrument, granularity, timestamp_utc)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_candles_time
            ON candles(instrument, granularity, timestamp_utc)
        """)
        conn.commit()
    finally:
        conn.close()

# OANDA api
def _oanda_headers() -> dict:
    # authorization headers for OANDA api requests
    return {
        "Authorization": f"Bearer {OANDA_API_TOKEN}",
        "Content-Type": "application/json",
    }

def fetch_candles_from_oanda(
        granularity: str,
        from_time: datetime,
        to_time: datetime,
        instrument: str = INSTRUMENT,
) -> list[dict]:
    """
    fetch candles from OANDA v20 API
    Args:
        granularityy: "H1" or "M5"
        from_time: Start time (UTC, inclusive)
        to_time: End time (UTC, inclusive)
        instrument: e.g., "AUDJPY"
        
    Returns:
        List of raw candle dicts from OANDA
        Each contains 'time', 'mid' (with o/h/l/c), 'complete'
        
    Note:
        OANDA returns max 5000 candles per request
        for longer ranges, call this multiple times
    """
    url = f"{OANDA_API_URL}/v3/instruments/{instrument}/candles"

    params = {
        "granularity": granularity,
        "from": from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": to_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "price": "M",   # mid prices only
        "alignmentTimezone": "America/New_York",
        "dailyAlignment": 17,       # 5pm NY alignment
    }

    response = requests.get(url, headers=_oanda_headers(), params=params)
    response.raise_for_status()

    data = response.json()
    return data.get("candles", [])

# storage
def store_candles(
    candles: list[dict],
    granularity: str,
    instrument: str = INSTRUMENT,
    db_path: Path = CANDLE_DB_PATH,
) -> int:
    """
    store OANDA candles in SQLite
    uses INSERT OR REPLACE to handle duplicates gracefully
    returns count of candles stored
    """
    if not candles:
        return 0
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for c in candles:
            cursor.execute(
                """
                INSERT OR REPLACE INTO candles
                (instrument, granularity, timestamp_utc, open, high, low, close, complete)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instrument,
                    granularity,
                    c["time"],
                    c["mid"]["o"],
                    c["mid"]["h"],
                    c["mid"]["l"],
                    c["mid"]["c"],
                    1 if c["complete"] else 0,
                ),
            )
        conn.commit()
        return len(candles)
    finally:
        conn.close()

def get_candles(
        granularity: str,
        from_time: datetime,
        to_time: datetime,
        instrument: str = INSTRUMENT,
        db_path: Path = CANDLE_DB_PATH,
        complete_only: bool = True,
) -> list[Candle]:
    """
    retrieve candles from local SQLite storage
    Args:
        granularity: "H1" or "M5"
        from_time: Start time (UTC, inclusive)
        to_time: End time (UTC, inclusive)
        complete_only: if true, only return complete candles
    Returns:
        list of Candle obkects, sorted by timestamp ascending
    """
    conn = sqlite3.connect(db_path)
    try:
        query = """
            SELECT timestamp_utc, open, high, low, close
            FROM candles
            WHERE instrument = ?
                AND granularity = ?
                AND timestamp_utc >= ?
                AND timestamp_utc <= ?
        """
        params = [
            instrument,
            granularity,
            from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            to_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ]

        if complete_only:
            query += " AND complete = 1"
        query += " ORDER BY timestamp_utc ASC"

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        return [
            Candle(
                timestamp=datetime.fromisoformat(row[0].replace("Z", "+00:00")),
                open=Decimal(row[1]),
                high=Decimal(row[2]),
                low=Decimal(row[3]),
                close=Decimal(row[4]),
            )
            for row in rows
        ]
    finally:
        conn.close()

# high-level fetch + store
def fetch_and_store_candles(
        granularity: str,
        from_time: datetime,
        to_time: datetime,
        instrument: str = INSTRUMENT,
) -> int:
    """
    fetch candles from OANDA and store locally
    handles OANDA's 5000 candle limit by chunking requests
    returns total count of candles stored
    """

    init_db()

    # determine chunk size based on granularity
    if granularity == "H1":
        chunk_delta = timedelta(days=200)   # ~4800 hourly candles
    elif granularity == "M5":
        chunk_delta = timedelta(days=17)    # ~4896 5-min candles
    else:
        chunk_delta = timedelta(days=17)

    total_stored = 0
    chunk_start = from_time

    while chunk_start < to_time:
        chunk_end = min(chunk_start + chunk_delta, to_time)

        candles = fetch_candles_from_oanda(
            granularity=granularity,
            from_time=chunk_start,\
            to_time=chunk_end,
            instrument=instrument,
        )

        stored = store_candles(candles, granularity, instrument)
        total_stored += stored

        chunk_start = chunk_end

    return total_stored


# convenience functions for session data
def get_range_candle(session_date, db_path: Path = CANDLE_DB_PATH) -> Candle | None:
    """
    Get the 7pm-8pm NY range candle for a session date
    Args:
        session_date: date object (NY timezone date)
    Returns:
        the 1H candle starting at 7pm NY, or None if not found
    """
    # 7pm NY on the session date
    range_start_ny = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        19, 0, 0,
        tzinfo=NY,
    )
    # convert to UTC for querying
    range_start_utc = range_start_ny.astimezone(tz=None).replace(tzinfo=None)

    # query expects UTC string in ISO format
    # the candle timestamp is its open time
    candles = get_candles(
        granularity="H1",
        from_time=range_start_utc,
        to_time=range_start_utc,    # exact match
        db_path=db_path,
    )

    return candles[0] if candles else None

def get_session_5m_candles(
        session_date,
        up_to: datetime | None = None,
        db_path: Path = CANDLE_DB_PATH,
) -> list[Candle]:
    """
    get all 5M candles for a session's hunt period
    args:
        session_date: date object (NY timezone date)
        up_to: if provided, only get candles up to this time (UTC)
                if None, gets all candles through force_close
    returns:
        list of 5M candles from 8pm to force_close (or up_to)
    """

    from .scheduler import get_session_times # avoid circular import
    times = get_session_times(session_date)
    if times is None:
        return []
    # hunt starts at 8pm NY (range_end)
    hunt_start_utc = times.hunt_start

    if up_to is not None:
        end_utc = up_to
    else:
        end_utc = times.force_close

    return get_candles(
        granularity="M5",
        from_time=hunt_start_utc,
        to_time=end_utc,
        db_path=db_path,
    )

# design points
# pricesa stored as text, as sqlite doesn't have decimal type, and string storage preserves OANDA's exact precision
# INSERT OR REPLACE: re-fetching same time range is safe, duplicates are handled
# chunking: OANDA limits 5000 candles per request. the function auto-chunks larger ranges
# alignmentTimezone and dailyAlignment ensure hourly candles align to NY hours. The 7pm candle is exactly 7:00:00 to 7:59:59pm NY