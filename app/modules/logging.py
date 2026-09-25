import logging
import os

# Load log level from environment variables
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
configured_level = logging.getLevelName(log_level)
if not isinstance(configured_level, int):
    configured_level = logging.INFO

# Configure the logging format
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Set up basic logging
logging.basicConfig(
    # Keep dependency DEBUG logs out: Telegram may include its bot token in URLs.
    level=max(configured_level, logging.INFO),
    format=log_format,
)

# Create a logger instance for modules to use
logger = logging.getLogger("gpt_bot")
logger.setLevel(configured_level)
