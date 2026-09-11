"""
Session timing and scheduling logic
All session boundaries are defined in America/New_York timezone
Functions return UTC datetimes for use with OANDA API and storage
"""

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from .config import NY
from .types import SessionTimes

def get_session(session_date: date) -> SessionTimes | None:
    """
    get all key timestamps for a trading session
    a session "belongs to" the date when its range candle occurs (7pm NY)
    the session runs from 7pm that day until force_close the next day
    args:
        session_date: the NYY date identifying this session
    returns:
        SessionTimes with all boundaries in UTC, or None if no session
        on this date (Friday or Saturday)
    session schedule:
        -sunday: 7pm Sun -> 6:59 Mon(normal)
        same schedule for Monday until Wednesday close
        -thursday: 7pm Thu -> 3:59pm Fri (early close)
        -friday: no session (market closes 5pm)
        -saturday: no session
    """
    weekday = session_date.weekday() # Monday=0, Sunday=6

    # no sessions on Friday or Saturday
    if weekday in (4, 5): # fri=4, sat=5
        return None

    # range candle: 7pm to 8pm NY on session_date
    range_start_ny = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        19, 0, 0,        # 7pm
        tzinfo=NY,
    )
    range_end_ny = range_start_ny + timedelta(hours=1) #8pm

    # hunting period begings at 8pm
    hunt_start_ny = range_end_ny

    # force close time depends on day of week, so adjusting for that
    next_day = session_date + timedelta(days=1)

    if weekday == 3:    # thursday -> force close at 3:59pm Friday
        force_close_ny = datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            15, 59, 0,  # 3:59pm
            tzinfo=NY,
        )
    else: # all other days -> force close at 6:59pm enxt day
        force_close_ny = datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            18, 59, 0, # 6:59pm
            tzinfo=NY,
        )
    # converting all times to UTC for storage/API use
    return SessionTimes(
        session_date=session_date,
        range_start=range_start_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        range_end=range_end_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        hunt_start=range_end_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        force_close=force_close_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
    )

def get_current_session_date(now_utc: datetime) -> date | None:
    """
    determining current session belonging
    args:
        now_utc: current time in UTC
    returns:
        session_date (NY date) of active session, or None if no session active (weekend/between sessions)
    """

    # ensure working with UTC, then convert to NY
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY)

    weekday_ny = now_ny.weekday()
    hour_ny = now_ny.hour()

    # saturday: no session
    if weekday_ny == 5:
        return None

    # sunday before 7pm: no session yet (market opens 5pm, range at 7pm)
    if weekday_ny == 6 and hour_ny < 19:
        return None

    # friday after 4pm: thursdays session over, no friday session
    if weekday_ny == 4 and hour_ny >= 16:
        return (now_ny.date() - timedelta(days=1))

    # 7pm or later: this days sesh
    if hour_ny >= 19:
        # but NOT friday or saturday
        return now_ny.date()

    # before 7pm: previous days session (if it exists)
    prev_date = now_ny.date() - timedelta(days=1)
    prev_weekday = prev_date.weekday()

    # prev day was fri or sat, then no session to continue
    if prev_weekday in (4, 5):
        return None

    return prev_date

def is_market_open(now_utcL: datetime) -> bool:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY)

    weekday = now_ny.weekday()
    hour = now_ny.hour

    if weekday == 5:
        return False
    if weekday == 6:
        return hour >= 17
    if weekday == 4:
        return hour < 17
    return True

def next_session_date(after_date: date) -> date:
    candidate = after_date + timedelta(days=1)
    while candidate.weekday() in (4, 5):
        candidate += timedelta(days=1)

    return candidate

def next_range_start(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY)

    candidate_ny = datetime(
        now_ny.year,
        now_ny.month,
        now_ny.day,
        19, 0, 0,
        tzinfo=NY,
    )

    if now_ny >= candidate_ny:
        candidate_ny += timedelta(days=1)

    while candidate_ny.weekday() in (4, 5):
        candidate_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

def session_status_at(now_utc: datetime, session: SessionTimes) -> str:
    if now_utc.tzinfo is not None:
        now_utc = now_utc.replace(tzinfo=None)

    if now_utc < session.range_start:
        return "before_range"
    elif now_utc < session.range_end:
        return "in_range"
    elif now_utc < session.force_close:
        return "hunting"
    elif now_utc < session.force_close + timedelta(minutes=1):
        return "force_close"
    else:
        return "after"

# key points
# weekday() convention used
# DST handled automatically 