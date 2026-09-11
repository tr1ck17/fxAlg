import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent # going up three levels gets us to project root where .env lives
load_dotenv(PROJECT_ROOT / ".env")

# OANDA api
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN")
OANDA_API_URL = os.getenv("OANDA_API_URL", "https://api-fxpractice.oanda.com")

# telegram alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# timezone (not fixed UTC offset)
NY = ZoneInfo("America/New_York")

# instrument
INSTRUMENT = "AUD_JPY"

# storage paths
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
CANDLE_DB_PATH = DATA_DIR / "candles.db"

# ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)