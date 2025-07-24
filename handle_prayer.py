# handle_prayer.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from state import (
    PRAY_TEXT,
    PRAY_AUDIO,
)
from database import (
    get_request_by_id,
    get_all_prayer_requests,
    get_user_groups,
    get_group_title,
    mark_prayed,
    get_all_prayed_users,
    mark_joined,
    unmark_joined,
    get_joined_users,
)


async def request_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != 'private':
        return

    user_id = update.effective_user.id
    viewer_groups = get_user_groups(user_id)

    # Fetch all prayer requests
    all_requests = get_all_prayer_requests()
    
    # Filter out user's own requests and keep only those in shared groups
    filtered_requests = []
    for r in all_requests:
        if r.user_id == user_id:
            continue

        creator_groups = get_user_groups(r.user_id)
        shared_groups = viewer_groups & creator_groups
        if shared_groups:
            filtered_requests.append(r)

    if not filtered_requests:
        await update.message.reply_text('No prayer requests from others are available.')
        return
    
    # Group requests by username (anonymous usernames will be sorted at the end)
    requests_by_user = {}
    for r in filtered_requests:
        key = r.username if not r.is_anonymous else None
        requests_by_user.setdefault(key, []).append(r)

    # Sort users alphabetically, placing None (anonymous) last
    sorted_usernames = sorted(
        [u for u in requests_by_user.keys() if u is not None],
        key=lambda x: x.lower()
    )
    if None in requests_by_user:
        sorted_usernames.append(None)
    
    all_prayed = get_all_prayed_users()

    # Send group requests by user
    for username in sorted_usernames:
        requests = requests_by_user[username]
        # Group by chat (group_id)
        group_requests_by_chat = {}
        for r in requests:
            creator_groups = get_user_groups(r.user_id)
            shared_groups = viewer_groups & creator_groups
            for gid in shared_groups:
                group_requests_by_chat.setdefault(gid, []).append(r)

        # For each group, send message
        for gid, reqs in group_requests_by_chat.items():
            group_name = get_group_title(gid)
            title_username = "Anonymous" if username is None else username
            keyboard_buttons = []
            for r in reqs:
                prayed_users = all_prayed.get(r.id, set())
                prayed = " ✔️" if user_id in prayed_users else ""
                button_text = f"{title_username}: {r.text}{prayed}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f'public_view_{r.id}')])
            await update.message.reply_text(
                f"👥 <b>-- Requests from {title_username} in {group_name} --</b>",
                reply_markup=InlineKeyboardMarkup(keyboard_buttons),
                parse_mode=ParseMode.HTML
            )

async def handle_public_request_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = query.data.split('_', 2)[2]
    req = get_request_by_id(req_id)
    joined_users = get_joined_users(req.id)
    joined = query.from_user.id in joined_users
    join_cb = f'unjoin_{req.id}' if joined else f'join_{req.id}'
    keyboard = [
        [InlineKeyboardButton('Mark as prayed', callback_data=f'pray_{req.id}')],
        [InlineKeyboardButton('Send a written prayer', callback_data=f'textpray_{req.id}')],
        [InlineKeyboardButton('Send an audio prayer', callback_data=f'audiopray_{req.id}')],
        [InlineKeyboardButton(joined and '➖ Unjoin' or '➕ Join', callback_data=join_cb)],
    ]
    await query.edit_message_text(
        f'*Prayer Request: *{req.text}',
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_request_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, req_id = query.data.split('_', 1)
    req = get_request_by_id(req_id)
    user_id = query.from_user.id
    if action == 'pray':
        mark_prayed(user_id, req.id)

        message = f'Someone prayed for your request: {req.text}'
        await context.bot.send_message(chat_id=req.user_id, text=message)

        notify = f'Someone prayed for a request you joined: {req.text}'
        joined_users = get_joined_users(req.id)
        for uid in joined_users:
            if uid != user_id:
                await context.bot.send_message(chat_id=uid, text=notify)
        await query.edit_message_text('✅ Marked as prayed.')

    elif action == 'join':
        mark_joined(user_id, req.id)
        await query.edit_message_text('✅ You joined the prayer request.')
    
    elif action == 'unjoin':
        unmark_joined(user_id, req.id)
        await query.edit_message_text('✅ You left the prayer request.')

async def pray_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    
    query = update.callback_query
    await query.answer()
    req_id = query.data.split('_', 1)[1]
    context.user_data['praying_req'] = req_id
    await query.edit_message_text('✍️ Please send your prayer as a message.')
    return PRAY_TEXT

async def pray_text_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req_id = context.user_data.pop('praying_req', None)
    if req_id:
        req = get_request_by_id(req_id)
        message = (
            f'✍️ Someone sent a written prayer\n'
            f'<b>Request:</b> {req.text}\n'
            f'<b>Prayer:</b> {update.message.text}'
        )
        await context.bot.send_message(
            chat_id=req.user_id, 
            text=message, 
            parse_mode=ParseMode.HTML
        )
        await update.message.reply_text('✅ Your prayer was sent.')
    context.user_data.clear()
    return ConversationHandler.END

async def pray_audio_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    query = update.callback_query
    await query.answer()
    req_id = query.data.split('_', 1)[1]
    context.user_data['praying_req'] = req_id
    await query.edit_message_text('🎤 Please send your prayer as a voice message.')
    return PRAY_AUDIO

async def pray_audio_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req_id = context.user_data.pop('praying_req', None)
    if req_id and update.message.voice:
        req = get_request_by_id(req_id)
        caption = f'🎤 Someone sent an audio prayer\n<b>Request:</b> {req.text}'
        await context.bot.send_voice(
            chat_id=req.user_id,
            voice=update.message.voice.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML
        )
        await update.message.reply_text('✅ Your audio prayer was sent.')
    context.user_data.clear()
    return ConversationHandler.END
