import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from handle_request import (
    add_request_start,
    add_request_text,
    add_request_anon,
    my_requests_list,
    handle_my_request_action,
)
from handle_prayer import (
    request_list_command,
    handle_public_request_view,
    handle_request_actions,
    pray_text_start,
    pray_text_finish,
    pray_audio_start,
    pray_audio_finish,
)
from state import ADD_TEXT, ADD_ANON, PRAY_TEXT, PRAY_AUDIO
from database import init_db, save_user_group_membership, save_group_title

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


def _parse_bot_id() -> int:
    raw_bot_id = os.getenv("BOT_ID", "")
    if not raw_bot_id:
        return 0
    try:
        return int(raw_bot_id)
    except ValueError:
        return 0


BOT_ID = _parse_bot_id()
update_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not BOT_TOKEN:
        # Keep the function bootable and fail requests with a useful error.
        yield
        return

    await telegram_app.initialize()
    try:
        yield
    finally:
        await telegram_app.shutdown()


app = FastAPI(lifespan=lifespan)


# ======================
# Handlers (UNCHANGED)
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Hello! I am the Light Of Life prayer bot.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/help - Show help\n"
        "/add_request - Add a prayer request\n"
        "/my_requests_list - List and manage own prayer requests\n"
        "/request_list - List and pray for prayer requests\n"
        "/cancel - Cancel any ongoing conversation\n"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled task. You can start again anytime.")
    return ConversationHandler.END


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        return

    save_user_group_membership(user.id, chat.id)
    save_user_group_membership(BOT_ID, chat.id)
    save_group_title(chat.id, chat.title or f"Group {chat.id}")


# ======================
# Build Telegram App
# ======================

def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")

    application = Application.builder().token(BOT_TOKEN).build()

    add_request_conv = ConversationHandler(
        entry_points=[CommandHandler("add_request", add_request_start)],
        states={
            ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_request_text)],
            ADD_ANON: [CallbackQueryHandler(add_request_anon, pattern="^anon_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    pray_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pray_text_start, pattern="^textpray_")],
        states={PRAY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pray_text_finish)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    pray_audio_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pray_audio_start, pattern="^audiopray_")],
        states={PRAY_AUDIO: [MessageHandler(filters.VOICE, pray_audio_finish)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(add_request_conv)
    application.add_handler(pray_text_conv)
    application.add_handler(pray_audio_conv)
    application.add_handler(CommandHandler("my_requests_list", my_requests_list))
    application.add_handler(
        CallbackQueryHandler(handle_my_request_action, pattern="^(view_|remove_|back_to_list|add_new)")
    )
    application.add_handler(CommandHandler("request_list", request_list_command))
    application.add_handler(CallbackQueryHandler(handle_public_request_view, pattern="^public_view_"))
    application.add_handler(
        CallbackQueryHandler(handle_request_actions, pattern="^(pray_|join_|unjoin_|public_back_to_list)")
    )
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.ALL, handle_group_message))
    application.add_handler(CommandHandler("cancel", cancel))

    return application


telegram_app = build_application()


# ======================
# Webhook Endpoint
# ======================

@app.post("/api/webhook")
async def webhook(request: Request):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Missing BOT_TOKEN environment variable")

    try:
        init_db()
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request payload: {exc}") from exc

    try:
        update = Update.de_json(data, telegram_app.bot)
        if update is None:
            raise ValueError("Could not deserialize Telegram update")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Telegram update: {exc}") from exc

    try:
        # Prevent concurrent update handling from racing shared app state.
        async with update_lock:
            await telegram_app.process_update(update)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process update: {exc}") from exc

    return {"ok": True}