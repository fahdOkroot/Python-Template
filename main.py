import os
import json
import asyncio
import logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from keep_alive import keep_alive
from config import BOTS, OWNER_ID

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

WAITING_CONTENT = 1


# ── Message store ──

class MessageStore:
    def __init__(self, bot_name: str, default_messages: list):
        self.bot_name = bot_name
        self.path = DATA_DIR / f"messages_{bot_name.replace(' ', '_')}.json"
        self._messages = self._load(default_messages)

    def _normalize(self, msg) -> dict:
        if isinstance(msg, str):
            return {"type": "text", "content": msg}
        return msg

    def _load(self, defaults: list) -> list:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) == 3:
                        logger.info(f"[{self.bot_name}] Loaded messages from file.")
                        return [self._normalize(m) for m in data]
            except Exception as e:
                logger.warning(f"[{self.bot_name}] Could not load messages file: {e}")
        return [self._normalize(m) for m in defaults]

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._messages, f, ensure_ascii=False, indent=2)

    def get(self) -> list:
        return self._messages

    def set(self, index: int, msg: dict):
        self._messages[index] = msg
        self._save()


# ── Send a stored message to a user ──

async def send_stored_message(bot, chat_id: int, msg: dict):
    t = msg.get("type", "text")
    caption = msg.get("caption") or msg.get("content", "")
    file_id = msg.get("file_id")

    if t == "text":
        await bot.send_message(chat_id=chat_id, text=msg.get("content", ""), parse_mode="Markdown")
    elif t == "photo":
        await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
    elif t == "video":
        await bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
    elif t == "animation":
        await bot.send_animation(chat_id=chat_id, animation=file_id, caption=caption)
    elif t == "document":
        await bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
    elif t == "audio":
        await bot.send_audio(chat_id=chat_id, audio=file_id, caption=caption)
    elif t == "voice":
        await bot.send_voice(chat_id=chat_id, voice=file_id, caption=caption)
    else:
        await bot.send_message(chat_id=chat_id, text=str(msg), parse_mode="Markdown")


# ── Join request handler ──

def make_join_handler(bot_name: str, store: MessageStore):
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        join_request = update.chat_join_request
        user = join_request.from_user
        chat = join_request.chat
        logger.info(
            f"[{bot_name}] Join request from user {user.id} (@{user.username}) "
            f"in chat {chat.id} ({chat.title})"
        )
        for i, msg in enumerate(store.get(), start=1):
            try:
                await send_stored_message(context.bot, user.id, msg)
                logger.info(f"[{bot_name}] Sent message {i}/3 to user {user.id}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"[{bot_name}] Could not send message {i} to {user.id}: {e}")

    return handle_join_request


# ── Owner keyboard ──

def owner_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ رسالة 1", callback_data="edit_0"),
            InlineKeyboardButton("✏️ رسالة 2", callback_data="edit_1"),
            InlineKeyboardButton("✏️ رسالة 3", callback_data="edit_2"),
        ],
        [InlineKeyboardButton("👁 عرض الرسائل الحالية", callback_data="view")],
    ])


# ── /start handler ──

def make_start_handler(bot_name: str, store: MessageStore):
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user.id != OWNER_ID:
            await update.message.reply_text("👋 أهلاً! هذا البوت يعمل تلقائياً.")
            return
        await update.message.reply_text(
            f"👋 *مرحباً في لوحة تحكم {bot_name}*\n\nاختر ما تريد:",
            parse_mode="Markdown",
            reply_markup=owner_keyboard(bot_name),
        )
        return ConversationHandler.END

    return start


# ── Conversation: edit message via button ──

def make_conversation_handler(bot_name: str, store: MessageStore):

    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        if query.from_user.id != OWNER_ID:
            return ConversationHandler.END

        if query.data == "view":
            messages = store.get()
            lines = [f"📋 *الرسائل الحالية لـ {bot_name}:*\n"]
            for i, msg in enumerate(messages, start=1):
                t = msg.get("type", "text")
                preview = msg.get("content") or msg.get("caption") or ""
                lines.append(f"*رسالة {i}* ({t}):\n{preview}\n")
            await query.message.reply_text(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=owner_keyboard(bot_name),
            )
            return ConversationHandler.END

        slot = int(query.data.split("_")[1])
        context.user_data["editing_slot"] = slot
        context.user_data["bot_name"] = bot_name

        await query.message.reply_text(
            f"📩 أرسل المحتوى الجديد للرسالة *{slot + 1}*\n\n"
            "يمكنك إرسال: نص، صورة، فيديو، GIF، ملف صوتي أو مستند.\n"
            "للإلغاء أرسل /cancel",
            parse_mode="Markdown",
        )
        return WAITING_CONTENT

    async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.effective_user.id != OWNER_ID:
            return ConversationHandler.END

        slot = context.user_data.get("editing_slot")
        if slot is None:
            return ConversationHandler.END

        msg = update.message
        new_msg = {}

        if msg.photo:
            new_msg = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
        elif msg.video:
            new_msg = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
        elif msg.animation:
            new_msg = {"type": "animation", "file_id": msg.animation.file_id, "caption": msg.caption or ""}
        elif msg.document:
            new_msg = {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption or ""}
        elif msg.audio:
            new_msg = {"type": "audio", "file_id": msg.audio.file_id, "caption": msg.caption or ""}
        elif msg.voice:
            new_msg = {"type": "voice", "file_id": msg.voice.file_id, "caption": msg.caption or ""}
        elif msg.text:
            new_msg = {"type": "text", "content": msg.text}
        else:
            await msg.reply_text("❌ نوع المحتوى غير مدعوم. أرسل نصاً أو صورة أو فيديو.")
            return WAITING_CONTENT

        store.set(slot, new_msg)
        logger.info(f"[{bot_name}] Message {slot + 1} updated by owner. Type: {new_msg['type']}")

        await msg.reply_text(
            f"✅ *تم تحديث الرسالة {slot + 1} بنجاح!*",
            parse_mode="Markdown",
            reply_markup=owner_keyboard(bot_name),
        )
        return ConversationHandler.END

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(
            "❌ تم الإلغاء.",
            reply_markup=owner_keyboard(bot_name),
        )
        return ConversationHandler.END

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback)],
        states={
            WAITING_CONTENT: [
                MessageHandler(
                    filters.ALL & ~filters.COMMAND,
                    receive_content,
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )
    return conv


# ── Bot runner ──

async def run_bot(token: str, bot_name: str, default_messages: list) -> None:
    store = MessageStore(bot_name, default_messages)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(ChatJoinRequestHandler(make_join_handler(bot_name, store)))
    app.add_handler(CommandHandler("start", make_start_handler(bot_name, store)))
    app.add_handler(make_conversation_handler(bot_name, store))

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
