import os
import json
import asyncio
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
)
from keep_alive import keep_alive
from config import BOTS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))


# ── Message store: loads from file, falls back to config defaults ──

class MessageStore:
    def __init__(self, bot_name: str, default_messages: list):
        self.bot_name = bot_name
        self.default_messages = default_messages
        self.path = DATA_DIR / f"messages_{bot_name.replace(' ', '_')}.json"
        self._messages = self._load()

    def _load(self) -> list:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) == 3:
                        logger.info(f"[{self.bot_name}] Loaded messages from file.")
                        return data
            except Exception as e:
                logger.warning(f"[{self.bot_name}] Could not load messages file: {e}")
        return list(self.default_messages)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._messages, f, ensure_ascii=False, indent=2)

    def get(self) -> list:
        return self._messages

    def set(self, index: int, text: str):
        self._messages[index] = text
        self._save()


# ── Handlers ──

def make_join_handler(bot_name: str, store: MessageStore):
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        join_request = update.chat_join_request
        user = join_request.from_user
        chat = join_request.chat

        logger.info(
            f"[{bot_name}] Join request from user {user.id} (@{user.username}) "
            f"in chat {chat.id} ({chat.title})"
        )

        for i, message in enumerate(store.get(), start=1):
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


def make_setmsg_handler(bot_name: str, store: MessageStore):
    async def setmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if OWNER_ID == 0:
            await update.message.reply_text(
                "⚠️ لم يتم تعيين OWNER\\_ID في الـ Secrets بعد.",
                parse_mode="Markdown",
            )
            return

        if user.id != OWNER_ID:
            await update.message.reply_text("🚫 هذا الأمر للمالك فقط.")
            return

        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "📝 *طريقة الاستخدام:*\n`/setmsg 1 نص الرسالة الجديدة`\n\nالرقم يكون 1 أو 2 أو 3",
                parse_mode="Markdown",
            )
            return

        try:
            msg_num = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ الرقم يجب أن يكون 1 أو 2 أو 3.")
            return

        if msg_num not in (1, 2, 3):
            await update.message.reply_text("❌ الرقم يجب أن يكون 1 أو 2 أو 3.")
            return

        new_text = " ".join(args[1:])
        store.set(msg_num - 1, new_text)
        logger.info(f"[{bot_name}] Message {msg_num} updated by owner.")

        await update.message.reply_text(
            f"✅ *تم تحديث الرسالة {msg_num} بنجاح!*\n\n{new_text}",
            parse_mode="Markdown",
        )

    return setmsg


def make_viewmsg_handler(bot_name: str, store: MessageStore):
    async def viewmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if OWNER_ID != 0 and user.id != OWNER_ID:
            await update.message.reply_text("🚫 هذا الأمر للمالك فقط.")
            return

        messages = store.get()
        text = f"📋 *الرسائل الحالية لـ {bot_name}:*\n\n"
        for i, msg in enumerate(messages, start=1):
            text += f"*رسالة {i}:*\n{msg}\n\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    return viewmsg


# ── Bot runner ──

async def run_bot(token: str, bot_name: str, default_messages: list) -> None:
    store = MessageStore(bot_name, default_messages)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(ChatJoinRequestHandler(make_join_handler(bot_name, store)))
    app.add_handler(CommandHandler("setmsg", make_setmsg_handler(bot_name, store)))
    app.add_handler(CommandHandler("viewmsg", make_viewmsg_handler(bot_name, store)))

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
