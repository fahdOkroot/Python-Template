import os
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    ContextTypes,
)
from keep_alive import keep_alive
from config import BOTS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def make_handler(bot_name: str, messages: list):
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        join_request = update.chat_join_request
        user = join_request.from_user
        chat = join_request.chat

        logger.info(
            f"[{bot_name}] Join request from user {user.id} (@{user.username}) "
            f"in chat {chat.id} ({chat.title})"
        )

        for i, message in enumerate(messages, start=1):
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=message,
                    parse_mode="Markdown",
                )
                logger.info(f"[{bot_name}] Sent message {i}/3 to user {user.id}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"[{bot_name}] Could not send message {i} to user {user.id}: {e}")

    return handle_join_request


async def run_bot(token: str, bot_name: str, messages: list) -> None:
    app = ApplicationBuilder().token(token).build()
    app.add_handler(ChatJoinRequestHandler(make_handler(bot_name, messages)))

    logger.info(f"[{bot_name}] Starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info(f"[{bot_name}] Running and listening for join requests.")
    await asyncio.Event().wait()


async def run_all() -> None:
    tasks = []
    for bot_cfg in BOTS:
        token_env = bot_cfg["token_env"]
        token = os.environ.get(token_env)
        if not token:
            logger.warning(f"Skipping bot — secret '{token_env}' not found in environment.")
            continue
        tasks.append(run_bot(token, bot_cfg["name"], bot_cfg["messages"]))

    if not tasks:
        logger.error("No bots configured. Add tokens to Secrets and update config.py.")
        return

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(run_all())
