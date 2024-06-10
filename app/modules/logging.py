import logging
import os

# Load log level from environment variables
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure the logging format
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Set up basic logging
logging.basicConfig(
    level=logging.getLevelName(log_level),
    format=log_format,
)

# Create a logger instance for modules to use
logger = logging.getLogger("gpt_bot")
