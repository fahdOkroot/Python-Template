import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    ContextTypes,
)
from keep_alive import keep_alive

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "✨ *Welcome, and thank you for joining our community!*\n\n"
    "We're truly delighted to have you with us. This is a space built on "
    "respect, curiosity, and shared passion — and you are now a part of it.\n\n"
    "Feel free to explore, engage, and make yourself at home. "
    "Great things happen when the right people come together. 🌟"
)


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_request = update.chat_join_request
    user = join_request.from_user
    chat = join_request.chat

    logger.info(
        f"Join request from user {user.id} (@{user.username}) "
        f"for chat {chat.id} ({chat.title})"
    )

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=WELCOME_MESSAGE,
            parse_mode="Markdown",
        )
        logger.info(f"Welcome DM sent to user {user.id}")
    except Exception as e:
        logger.warning(f"Could not send DM to user {user.id}: {e}")

    try:
        await join_request.approve()
        logger.info(f"Approved join request for user {user.id} in chat {chat.id}")
    except Exception as e:
        logger.error(f"Failed to approve join request for user {user.id}: {e}")


def main() -> None:
    bot_token = os.environ["BOT_TOKEN"]

    keep_alive()

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

    logger.info("Bot is starting — polling for updates...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
