import os
from pathlib import Path
from .logging import logger

# Load environment variables with defaults
openai_api_key = os.getenv("OPENAI_API_KEY")
telegram_api_token = os.getenv("TELEGRAM_BOT_TOKEN")
gpt_system_role = os.getenv("GPT_SYSTEM_ROLE", "You are a helpful assistant.")
gpt_model_name = os.getenv("GPT_MODEL_NAME", "gpt-3.5-turbo-1106")
log_level = os.getenv("LOG_LEVEL", "INFO")
allowed_chat_ids = os.getenv("ALLOWED_CHAT_IDS", "any").split(",")
locations_file_name = os.getenv("LOCATIONS_FILE_NAME", "/tmp/data/locations.csv")
country_code = os.getenv("COUNTRY_CODE", "GB")

# Define paths for static data files
base_dir = Path(__file__).resolve().parent.parent.parent
data_dir = base_dir / "app" / "data"
help_file = data_dir / "help.txt"
welcome_file = data_dir / "welcome.txt"

# Load help text
help_text = "Sorry, the help file is not available at the moment."
if help_file.exists():
    help_text = help_file.read_text()

# Load welcome text
welcome_text = "Welcome to the chat!"
if welcome_file.exists():
    welcome_text = welcome_file.read_text()

# Log configuration details (sensitive data excluded from logs)
logger.info("Application settings loaded:")
logger.info(f"gpt_system_role: {gpt_system_role}")
logger.info(f"gpt_model_name: {gpt_model_name}")
logger.info(f"log_level: {log_level}")
logger.info(f"allowed_chat_ids: {allowed_chat_ids}")
