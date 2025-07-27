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
    get_prayer_requests_by_user,
    get_joined_requests_by_user,
    insert_prayer_request,
    get_request_by_rid,
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
    
    req = PrayerRequest(
        id=str(uuid4()),
        user_id=user.id,
        username=user.username or f"user_{user.id}",
        text=text,
        is_anonymous=is_anon,
    )
    insert_prayer_request(req)
    
    # Find shared groups of user and bot
    user_gs = get_user_groups(user.id)
    bot_gs = get_user_groups(BOT_ID)
    shared_groups = user_gs & bot_gs

    if not shared_groups:
        await query.edit_message_text(
            "⚠️ You are not in any shared groups with the bot. Your request will only be visible to you."
        )
    else:
        # Notify all groups where the bot is a member
        for group_id in shared_groups:
            message = (
                f"<b>-- New prayer request --</b>\n"
                f"Private message the bot and use /requests_list to view it.\n"
                f"Let's keep each other in prayer!\n\n"
            )
            await context.bot.send_message(
                chat_id=group_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
    if context.user_data.pop("came_from_list", False):
        await query.edit_message_text("✅ Added. Returning to your request list...")
        return await my_requests_list(update, context)
    else:
        await query.edit_message_text("✅ Your prayer request has been added.")
        return ConversationHandler.END

# --- List user's own prayer requests ---
async def my_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != 'private':
        return

    user_id = update.effective_user.id
    my_requests = get_prayer_requests_by_user(user_id)
    joined_request_ids = get_joined_requests_by_user(user_id)
    joined_requests = [req for rid in joined_request_ids if (req := get_request_by_rid(rid)) is not None]

    keyboard = []

    # Own requests
    if my_requests:
        for req in my_requests:
            keyboard.append([InlineKeyboardButton(f"📌 {req.text[:30]}", callback_data=f"view_{req.id}")])

    # Joined requests
    if joined_requests:
        keyboard.append([InlineKeyboardButton(" ", callback_data="noop")])  # spacing
        for req in joined_requests:
            text = f"{req.username}: {req.text[:30]}" if req.username else req.text[:30]
            keyboard.append([InlineKeyboardButton(f"🤝 {text}", callback_data=f"view_{req.id}")])

    keyboard.append([InlineKeyboardButton("➕ Add New Request", callback_data="add_new")])

    if not my_requests and not joined_requests:
        text = "😕 You haven’t made or joined any prayer requests yet."
    else:
        text = "<b>-- Your Prayer Requests --</b>"

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    elif update.message:
        await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

# --- Handle view and removal of user's requests ---
async def handle_my_request_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "add_new":
        context.user_data["came_from_list"] = True
        await query.edit_message_text("Please type your new prayer request:")
        return ADD_TEXT
    
    if data.startswith("view_"):
        req_id = data.split("_", 1)[1]
        req = get_request_by_rid(req_id)
        if not req:
            return await query.edit_message_text("⚠️ This request no longer exists.")
        if req.user_id != user_id:
            return await query.edit_message_text("❌ You do not own this request.")
        
        keyboard = [
            [InlineKeyboardButton("❌ Remove", callback_data=f"remove_{req.id}")],
            [InlineKeyboardButton("Back", callback_data="back_to_list")]
        ]
        return await query.edit_message_text(
            f"<b>-- Prayer Request --</b>\n\n{req.text}\n",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    if data.startswith("remove_"):
        req_id = data.split("_", 1)[1]
        req = get_request_by_rid(req_id)
        if req and req.user_id == user_id:
            delete_request_by_id(req_id)
            return await my_requests_list(update, context)
        else:
            await query.edit_message_text("❌ Could not remove the request.")
        return ConversationHandler.END
    
    if data == "back_to_list":
        return await my_requests_list(update, context)