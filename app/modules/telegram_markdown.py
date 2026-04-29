from telegram import MessageEntity
from telegramify_markdown import convert, split_entities


MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def _to_telegram_entity(entity) -> MessageEntity:
    data = entity.to_dict() if hasattr(entity, "to_dict") else dict(entity)
    return MessageEntity.de_json(data, bot=None)


def markdown_to_telegram_messages(markdown_text: str) -> list[tuple[str, list[MessageEntity]]]:
    """Convert Markdown into Telegram text + MessageEntity chunks."""
    text, entities = convert(markdown_text or "")
    chunks = split_entities(text, entities, max_utf16_len=MAX_TELEGRAM_MESSAGE_LENGTH)
    return [
        (chunk_text, [_to_telegram_entity(entity) for entity in chunk_entities])
        for chunk_text, chunk_entities in chunks
    ]
