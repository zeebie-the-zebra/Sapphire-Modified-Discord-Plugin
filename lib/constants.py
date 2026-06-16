"""Shared constants for the Leona Discord daemon."""

BATCH_DELAY_DEFAULT = 8.0
HISTORY_LIMIT = 100          # cached / mention-map depth
DEFAULT_INJECT_LIMIT = 25    # messages sent to the LLM as "Recent chat"
DEFAULT_LINE_MAX_CHARS = 280 # per-line cap in injected transcript
DISCORD_MSG_LIMIT = 2000
MAX_REACTED_ENTRIES = 2_000
CONNECT_COOLDOWN = 30  # seconds between full reconnect cycles
