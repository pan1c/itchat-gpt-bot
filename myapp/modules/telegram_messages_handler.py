from .logging import logging
from .settings import telegram_api_token, help_text, welcome_text
from .openai_conversation_handler import generate_response, generate_image

from telegram import __version__ as TG_VER
from telegram import ForceReply
from telegram import Update
from telegram.ext import Application
from telegram.ext import CommandHandler
from telegram.ext import ContextTypes
from telegram.ext import filters
from telegram.ext import MessageHandler


try:

    from telegram import __version_info__

except ImportError:

    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):

    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )

# Define a few command handlers. These usually take the two arguments update and

# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""

    user = update.effective_user

    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""


    await update.message.reply_html(help_text, disable_web_page_preview=True)

async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when a new user joins the chat."""
    user = update.effective_user

    await update.message.reply_html(
        rf"Hi {user.mention_html()} {welcome_text}",
    )

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and generate a response using GPT-3."""
    logging.info(update)
    question = update.message.text
    logging.info(question)

    response_text = await generate_response(question)

    await update.message.reply_text(response_text)

# image_generation command, aka DALLE
async def image_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # remove dalle command from message
    message = update.effective_message.text.replace("/imagine", "")
    logging.info(message)

    # send prompt to openai image generation and get image url
    image_url=generate_image(message)
    logging.info(image_url)
    

    # if exceeds use limit, send message instead
    if image_url is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Something went wrong. Please try again later."
        )
    else:
        # sending typing action
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="upload_document"
        )
        # send file to user
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption = f"{message} (Generated by DALLE)($0.018 / image)"
        )




def main() -> None:
    """Start the bot."""

    # Create the Application and pass it your bot's token.

    application = Application.builder().token(telegram_api_token).build()

    # on different commands - answer in Telegram

    application.add_handler(CommandHandler("start", start))

    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CommandHandler("imagine", image_generation))

    application.add_handler(CommandHandler("welcome", welcome_message))
    

    # on non command i.e message - run "handle_message"

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    # on new chat members - send welcome message

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))

    # Run the bot until the user presses Ctrl-C

    application.run_polling()

if __name__ == "__main__":

    main()



