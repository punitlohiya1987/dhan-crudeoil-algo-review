
# ==========================================================
# DHAN CRUDEOILM - CENTRAL CONFIGURATION
# VERSION 5.1 - CLOUDHQ SAFE CONFIG
#
# ACTIVE CONTRACT: DECEMBER 2026
# EXCHANGE: MCX_COMM
#
# DEFAULT DIRECTION: SELL
# ONE LOT PER ENTRY
# LOT SIZE: 10
# GRID: 100 POINTS
# COMMON SL DISTANCE: 100 POINTS
#
# LIVE TRADING: DISABLED
# ORDER PLACEMENT: DISABLED
# SL MODIFICATION: DISABLED
# POSITION CONVERSION: DISABLED
# ==========================================================


# ==========================================================
# DHAN CREDENTIALS
# ==========================================================
# Intentionally blank.
# Do not paste actual credentials here.
# CloudHQ-supported secret integration is still required.

DHAN_CLIENT_ID = ""
DHAN_ACCESS_TOKEN = ""


# ==========================================================
# ACTIVE FUTURES CONTRACT
# ==========================================================

ACTIVE_SYMBOL = "CRUDEOILM-18Dec2026-FUT"
ACTIVE_EXPIRY = "2026-12-18"
SECURITY_ID = "576265"
ACTIVE_SECURITY_ID = "576265"
EXCHANGE_SEGMENT = "MCX_COMM"


# ==========================================================
# STRATEGY DIRECTION
# ==========================================================

DIRECTION = "SELL"


# ==========================================================
# LOT CONFIGURATION
# ==========================================================

LOT_SIZE = 10
LOTS_PER_ENTRY = 1
QUANTITY_PER_ENTRY = LOT_SIZE * LOTS_PER_ENTRY


# ==========================================================
# GRID CONFIGURATION
# ==========================================================

GRID_POINTS = 100
STOP_LOSS_POINTS = 100

# Provisional setting; not yet confirmed.
MAX_ENTRIES = 10


# ==========================================================
# PRODUCT CONFIGURATION
# ==========================================================

PRODUCT_TYPE = "INTRADAY"

SUPPORTED_PRODUCT_TYPES = (
    "MARGIN",
    "INTRADAY",
)


# ==========================================================
# OVERNIGHT RISK LIMITS
# ==========================================================

MAXIMUM_OVERNIGHT_MARGIN_LOTS = 3
MORNING_SL_CHECK_TIME = "09:00"
SQUARE_OFF_TIME = "23:15"
EXPIRY_ROLLOVER_DAYS = 10


# ==========================================================
# EXECUTION SETTINGS
# ==========================================================

POLL_INTERVAL_SECONDS = 15
MAX_EXECUTION_HOURS = 9.8
STATE_FILE = "state.json"


# ==========================================================
# TRADING SAFETY SWITCHES
# ==========================================================

TRADING_MODE = "PAPER"

LIVE_TRADING_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
SL_MODIFICATION_ENABLED = False
POSITION_CONVERSION_ENABLED = False


# ==========================================================
# DURABLE STATE SAFETY
# ==========================================================

DURABLE_STATE_VERIFIED = False
REQUIRE_DURABLE_STATE = True


# ==========================================================
# ENGINE RELEASE SWITCHES
# ==========================================================

LIVE_ENGINE_RELEASED = False
LIVE_SL_MODIFICATION_RELEASED = False
AUTOMATIC_RETRY_ENABLED = False
CANCEL_AND_REPLACE_ENABLED = False


# ==========================================================
# MANUAL CANCELLATION PROTECTION
# ==========================================================

MANUAL_CANCELLATION_LOCK_ENABLED = True
RESET_CANCELLATION_LOCK_ONLY_ON_FRESH_RUN = True


# ==========================================================
# POSITION ENROLLMENT SAFETY
# ==========================================================

AUTO_ENROLL_EXISTING_POSITIONS = False
MANAGE_ONLY_REGISTERED_CYCLE_POSITIONS = True


# ==========================================================
# ORDER SAFETY
# ==========================================================

ALLOW_MARKET_ENTRY = False
ALLOW_LIMIT_ENTRY = True
ALLOW_STOP_LOSS_MARKET = True
ALLOW_AUTOMATIC_ORDER_RETRY = False
ALLOW_AUTOMATIC_ORDER_CANCELLATION = False


# ==========================================================
# DATA RATE SAFETY
# ==========================================================

MINIMUM_LTP_POLL_SECONDS = 15
MAXIMUM_API_RETRIES = 0
