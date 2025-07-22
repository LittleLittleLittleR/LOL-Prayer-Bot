# handle_request.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from dataclasses import dataclass, field
from uuid import uuid4
from typing import Set, Dict
from dotenv import load_dotenv
import os
from state import (
    ADD_TEXT, 
    ADD_ANON,
    SELECT_VISIBILITY,
    SELECT_GROUP,
    user_groups,
    group_titles,
)

# Load environment variables
load_dotenv()

BOT_ID = int(os.getenv("BOT_ID"))

# Data model and store
@dataclass
class PrayerRequest:
    id: str
    text: str
    user_id: int
    username: str
    is_anonymous: bool
    joined_users: Set[int] = field(default_factory=set)
    prayed_users: Set[int] = field(default_factory=set)
    group_id: int | None = None
    visibility: str = "public"  # "public" or "group"

prayer_requests: Dict[str, PrayerRequest] = {}

async def add_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton('🌐 Public (anyone)', callback_data='vis_public')],
        [InlineKeyboardButton('👥 Group only', callback_data='vis_group')],
    ])
    await query.edit_message_text("Please choose visibility:", reply_markup=keyboard)
    return SELECT_VISIBILITY

async def select_visibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vis = query.data.split("_", 1)[1]
    user = query.from_user

    text = context.user_data.pop('new_request_text', None)
    is_anon = context.user_data.pop('is_anon', False)

    if not text:
        await query.edit_message_text("❌ Error: No text found for your prayer request.")
        return ConversationHandler.END

    if vis == "group":
        # Find shared groups of user and bot
        user_gs = user_groups.get(user.id, set())
        bot_gs = user_groups.get(BOT_ID, set())  # groups where bot is member
        shared_groups = user_gs & bot_gs

        if not shared_groups:
            await query.edit_message_text("⚠️ You are not in any group with the bot, so you can't add a group-only request.")
            return ConversationHandler.END

        # Create a prayer request for each shared group
        for gid in shared_groups:
            req = PrayerRequest(
                id=str(uuid4()),
                text=text,
                user_id=user.id,
                username=user.username or f"user_{user.id}",
                is_anonymous=is_anon,
                group_id=gid,
                visibility=vis
            )
            prayer_requests[req.id] = req

        await query.edit_message_text(f"✅ Your group-only prayer request has been added to {len(shared_groups)} group(s).")
        return ConversationHandler.END

    else:

        req = PrayerRequest(
            id=str(uuid4()),
            text=text,
            user_id=user.id,
            username=user.username or f"user_{user.id}",
            is_anonymous=is_anon,
            group_id=None,
            visibility=vis
        )

        prayer_requests[req.id] = req
        await query.edit_message_text("✅ Your prayer request has been added.")
        return ConversationHandler.END

async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_", 2)[2])

    data = context.user_data.pop('pending_request')
    req = PrayerRequest(
        id=str(uuid4()),
        text=data['text'],
        user_id=query.from_user.id,
        username=query.from_user.username or f"user_{query.from_user.id}",
        is_anonymous=data['is_anon'],
        group_id=group_id,
        visibility=data['visibility']
    )

    prayer_requests[req.id] = req
    await query.edit_message_text("✅ Your group-only prayer request has been added.")
    return ConversationHandler.END

# --- List user's own prayer requests ---
async def my_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    my_requests = [req for req in prayer_requests.values() if req.user_id == user_id]
    if not my_requests:
        await update.message.reply_text("You haven't added any prayer requests yet. Use /add_request to start.")
        return
    keyboard = [[InlineKeyboardButton(f"{req.text[:50]}", callback_data=f"view_{req.id}")] for req in my_requests]
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
        req = prayer_requests.get(req_id)
        if not req:
            return await query.edit_message_text("⚠️ This request no longer exists.")
        if req.user_id != user_id:
            return await query.edit_message_text("❌ You do not own this request.")
        keyboard = [[InlineKeyboardButton("❌ Remove", callback_data=f"remove_{req.id}")]]
        return await query.edit_message_text(
            f"📃 *Your Prayer Request: *{req.text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    if data.startswith("remove_"):
        req_id = data.split("_", 1)[1]
        req = prayer_requests.get(req_id)
        if req and req.user_id == user_id:
            prayer_requests.pop(req_id, None)
            return await query.edit_message_text("✅ Your request has been removed.")
        return await query.edit_message_text("❌ Could not remove the request.")