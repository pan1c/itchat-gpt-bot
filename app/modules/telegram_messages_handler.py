from io import BytesIO
from telegram import Update, ForceReply, MessageEntity
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
from .settings import telegram_api_token, help_text, welcome_text, allowed_chat_ids
from .openai_conversation_handler import generate_response, generate_image, reset_conversation
from .postcode_handler import process_postcode
from .telegram_markdown import markdown_to_telegram_messages
from .logging import logger

MAX_IMAGE_CAPTION_UTF16_LENGTH = 1024
IMAGE_CAPTION_PREFIX = "On this picture:\n"
MAX_REPLY_CONTEXT_LENGTH = 1500


def get_message_from_command(text: str) -> str:
    """Extract the message from a command."""
    return text.split(" ", 1)[1].strip() if " " in text else ""


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _build_image_caption(description: str) -> tuple[str, list[MessageEntity]]:
    max_description_length = MAX_IMAGE_CAPTION_UTF16_LENGTH - _utf16_length(IMAGE_CAPTION_PREFIX)
    suffix = "..."
    suffix_length = _utf16_length(suffix)

    if _utf16_length(description) > max_description_length:
        remaining_length = max_description_length - suffix_length
        truncated = []
        for character in description:
            character_length = _utf16_length(character)
            if character_length > remaining_length:
                break
            truncated.append(character)
            remaining_length -= character_length
        description = "".join(truncated) + suffix

    caption = f"{IMAGE_CAPTION_PREFIX}{description}"
    entity = MessageEntity(
        type="blockquote",
        offset=_utf16_length(IMAGE_CAPTION_PREFIX),
        length=_utf16_length(description),
    )
    return caption, [entity]


def _truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _get_user_label(user) -> str:
    if not user:
        return "Unknown user"

    name_parts = [part for part in (user.first_name, user.last_name) if part]
    display_name = " ".join(name_parts) or user.username or str(user.id)
    if user.username:
        return f"{display_name} (@{user.username})"
    return display_name


def _get_message_text(message) -> str:
    return (message.text or message.caption or "").strip()


def _add_reply_context(message, question: str) -> str:
    reply = message.reply_to_message
    if not reply:
        return question

    reply_text = _get_message_text(reply)
    if not reply_text:
        return question

    author = _get_user_label(reply.from_user)
    reply_context = _truncate_text(reply_text, MAX_REPLY_CONTEXT_LENGTH)
    user_message = question.strip() or "Please respond to the replied message."
    return (
        "The user replied to this Telegram message:\n"
        f"From: {author}\n"
        f"Message: {reply_context}\n\n"
        f"User message: {user_message}"
    )


def check_group(update: Update) -> bool:
    """Check if the user's chat ID is allowed."""
    chat_id_str = str(update.message.chat_id)
    if "any" in allowed_chat_ids or chat_id_str in allowed_chat_ids:
        logger.info(f"Chat ID {chat_id_str} allowed")
        return True
    logger.info(f"Chat ID {chat_id_str} not allowed")
    return False  # Fixed indentation



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_html(help_text, disable_web_page_preview=True)


async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /welcome command or new chat members."""
    users = update.message.new_chat_members if update.message.new_chat_members else [update.effective_user]
    for user in users:
        await update.message.reply_html(
            rf"Hi {user.mention_html()}! {welcome_text}",
            disable_web_page_preview=True,
        )


def _extract_activation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """Decide if the bot should respond, and strip the mention from the prompt."""
    message = update.message
    text = message.text or ""

    # Is current message a reply to a previous bot message?
    bot_id = context.bot.id
    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.id == bot_id:
        return True, text

    bot_username = f"@{context.bot.username}"
    for entity in message.entities or []:
        if entity.type != MessageEntity.MENTION:
            continue
        chunk = text[entity.offset : entity.offset + entity.length]
        if chunk.lower() == bot_username:
            cleaned = (text[: entity.offset] + text[entity.offset + entity.length :]).strip()
            return True, cleaned

    return False, text


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and generate a GPT response."""
    if not check_group(update):
        return

    activated, question = _extract_activation(update, context)
    if not activated:
        return
    question = _add_reply_context(update.message, question)
    if not question:
        question = "Hi"

    logger.info(f"Question: {question}")
    response_text = await generate_response(
        question=question,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )
    for text, entities in markdown_to_telegram_messages(response_text):
        await update.message.reply_text(
            text,
            entities=entities,
            disable_web_page_preview=True,
        )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the GPT conversation context for the current user in the current chat."""
    if not check_group(update):
        return

    was_cleared = reset_conversation(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )
    response_text = (
        "Conversation context cleared."
        if was_cleared
        else "There was no saved conversation context for you in this chat."
    )
    await update.message.reply_text(response_text)


async def image_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an image using DALL-E."""
    if not check_group(update):
        return

    # Extract the prompt from the command
    prompt = get_message_from_command(update.effective_message.text)
    if not prompt:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="No message provided. Please specify your prompt like this: /imagine a cat"
        )
        return

    logger.info(f"Image prompt: {prompt}")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Generating image for your prompt. Please wait..."
    )

    # Generate the image
    image_payload, revised_prompt, error_message = generate_image(prompt)
    if not image_payload:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Error: {error_message or 'Failed to generate image'}"
        )
        return

    # Send the generated image
    caption_text, caption_entities = _build_image_caption(revised_prompt or prompt)
    photo = image_payload
    if isinstance(image_payload, (bytes, bytearray)):
        photo = BytesIO(image_payload)
        photo.name = "generated.png"

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=photo,
        caption=caption_text,
        caption_entities=caption_entities,
    )


async def postcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /postcode command."""
    user = update.effective_user
    message = get_message_from_command(update.effective_message.text)
    response_text = process_postcode(
        user_id=user.id,
        username=user.username,
        firstname=user.first_name,
        lastname=user.last_name,
        message=message,
    )
    await update.message.reply_text(response_text)


def main() -> None:
    """Run the bot."""
    application = Application.builder().token(telegram_api_token).build()

    # Add handlers for various commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("welcome", welcome_message))  # Added /welcome command
    application.add_handler(CommandHandler("postcode", postcode))
    application.add_handler(CommandHandler("imagine", image_generation))
    application.add_handler(CommandHandler("reset", reset_command))

    # Add handler for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    # Add handler for new chat members
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
