# handle_request.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from uuid import uuid4
from dotenv import load_dotenv
import os
from state import (
    ADD_TEXT, 
    ADD_ANON,
    PrayerRequest,
)
from database import (
    get_user_requests,
    insert_prayer_request,
    get_request_by_id,
    delete_request_by_id,
    get_user_groups,
)

# Load environment variables
load_dotenv()

BOT_ID = int(os.getenv("BOT_ID"))


async def add_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != 'private':
        return
    
    context.user_data.clear()

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text('Please send me your prayer request.')
    elif update.message:
        await update.message.reply_text('Please send me your prayer request.')
    return ADD_TEXT

async def add_request_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['new_request_text'] = text
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton('Yes', callback_data='anon_yes')],
        [InlineKeyboardButton('No', callback_data='anon_no')],
    ])
    await update.message.reply_text('Would you like to stay anonymous?', reply_markup=keyboard)
    return ADD_ANON

async def add_request_anon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_anon = query.data == 'anon_yes'
    context.user_data['is_anon'] = is_anon

    user = query.from_user
    text = context.user_data.pop('new_request_text', None)

    if not text:
        await query.edit_message_text("❌ Error: No text found for your prayer request.")
        return ConversationHandler.END
    
    # Find shared groups of user and bot
    user_gs = get_user_groups(user.id)
    bot_gs = get_user_groups(BOT_ID)
    shared_groups = user_gs & bot_gs

    if not shared_groups:
        await query.edit_message_text("⚠️ You are not in any group with the bot, so you can't add a group-only request.")
        return ConversationHandler.END

    req = PrayerRequest(
        id=str(uuid4()),
        user_id=user.id,
        username=user.username or f"user_{user.id}",
        text=text,
        is_anonymous=is_anon,
    )

    insert_prayer_request(req)

    await query.edit_message_text("✅ Your prayer request has been added.")
    return ConversationHandler.END

# --- List user's own prayer requests ---
async def my_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != 'private':
        return

    user_id = update.effective_user.id
    my_requests = get_user_requests(user_id)
    if not my_requests:
        await update.message.reply_text("You haven't added any prayer requests yet. Use /add_request to start.")
        return
    keyboard = [[InlineKeyboardButton(f"{req['text'][:50]}", callback_data=f"view_{req['id']}")] for req in my_requests]
    keyboard.append([InlineKeyboardButton("➕ Add Request", callback_data="add_new")])
    await update.message.reply_text(
        "📝 Your Prayer Requests:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Handle view and removal of user's requests ---
async def handle_my_request_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "add_new":
        await query.edit_message_text("Redirecting to /add_request")
        return await add_request_start(update, context)

    if data.startswith("view_"):
        req_id = data.split("_", 1)[1]
        req = get_request_by_id(req_id)
        if not req:
            return await query.edit_message_text("⚠️ This request no longer exists.")
        if req.user_id != user_id:
            return await query.edit_message_text("❌ You do not own this request.")
        keyboard = [[InlineKeyboardButton("❌ Remove", callback_data=f"remove_{req.id}")]]
        return await query.edit_message_text(
            f"📃 *Your Prayer Request: *{req.text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    if data.startswith("remove_"):
        req_id = data.split("_", 1)[1]
        req = get_request_by_id(req_id)
        if req and req.user_id == user_id:
            delete_request_by_id(req_id)
            return await query.edit_message_text("✅ Your request has been removed.")
        return await query.edit_message_text("❌ Could not remove the request.")