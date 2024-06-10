import re
from .csv_writer import write_csv
from .settings import country_code
from .logging import logger

NO_POSTCODE_MSG = "No postcode provided. Please specify your postcode like this: /postcode SW1"
INVALID_POSTCODE_MSG = "Invalid postcode. Please specify your postcode like this: /postcode SW1"

def process_postcode(user_id, username, firstname, lastname, message):
    """Process the given postcode message and save it to CSV."""
    label = " ".join(filter(None, [firstname, lastname]))
    message = message.upper().replace(" ", "")

    if not message:
        return NO_POSTCODE_MSG

    # Validate postcode
    message = re.sub(r"[^A-Z0-9]", "", message)
    if not message:
        return INVALID_POSTCODE_MSG

    logger.info(f"User {user_id} submitted postcode: {message}")
    write_csv([{"id": user_id, "country": country_code, "postcode": message, "label": label}])
    return f"Thank you {username} for your UK postcode"
