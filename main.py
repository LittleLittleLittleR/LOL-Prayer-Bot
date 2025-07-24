# main.py
from telegram import Update
import asyncio
import platform
import os
from dotenv import load_dotenv

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
from state import (
    ADD_TEXT, 
    ADD_ANON,
    PRAY_TEXT, 
    PRAY_AUDIO,
)
from database import (
    init_db,
    save_user_group_membership,
    save_group_title,
)

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_ID = int(os.getenv("BOT_ID"))

# Windows asyncio fix
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text('Hello! I am the LOL Prayer Bot.')
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '/help - Show help\n'
        '/add_request - Add a prayer request\n'
        '/my_requests_list - List and manange your prayer requests\n'
        '/request_list - List and pray for prayer requests\n'
        '/stats - View stats\n'
        '/cancel - Cancel any ongoing conversation\n'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. You can start again anytime.")
    return ConversationHandler.END

# ─── Conversation Handlers ───────────────────────────────────────────────────
add_request_conv = ConversationHandler(
    entry_points=[CommandHandler('add_request', add_request_start)],
    states={
        ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_request_text)],
        ADD_ANON: [CallbackQueryHandler(add_request_anon, pattern='^anon_')],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

pray_text_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(pray_text_start, pattern='^textpray_')],
    states={PRAY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pray_text_finish)]},
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

pray_audio_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(pray_audio_start, pattern='^audiopray_')],
    states={PRAY_AUDIO: [MessageHandler(filters.VOICE, pray_audio_finish)]},
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        return

    # Save group membership
    save_user_group_membership(user.id, chat.id)
    save_user_group_membership(BOT_ID, chat.id)
    save_group_title(chat.id, chat.title or f"Group {chat.id}")
# ────────────────────────────────────────────────────────────────────────────────

def main():
    print('Starting the LOL Prayer Bot')
    app = Application.builder().token(BOT_TOKEN).build()

    # Basic commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))

    # Conversation flows
    app.add_handler(add_request_conv)
    app.add_handler(pray_text_conv)
    app.add_handler(pray_audio_conv)

    # My requests list and removal
    app.add_handler(CommandHandler('my_requests_list', my_requests_list))
    app.add_handler(CallbackQueryHandler(handle_my_request_action, pattern='^(view_|remove_|add_new)'))

    # Public request list and view/actions
    app.add_handler(CommandHandler('request_list', request_list_command))
    app.add_handler(CallbackQueryHandler(handle_public_request_view, pattern='^public_view_'))
    app.add_handler(CallbackQueryHandler(handle_request_actions, pattern='^(pray_|join_|unjoin_)'))

    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.ALL, handle_group_message))

    # Global cancel handler (responds anytime, inside or outside conversation)
    app.add_handler(CommandHandler("cancel", cancel))


    init_db()  # Initialize the database
    
    app.run_polling()

if __name__ == '__main__':
    main()