# handle_prayer.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from state import (
    PRAY_TEXT,
    PRAY_AUDIO,
)
from database import (
    get_request_by_rid,
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
            filtered_requests.append((r, shared_groups))

    if not filtered_requests:
        await update.message.reply_text('No prayer requests from others are available.')
        return

    all_prayed = get_all_prayed_users()

    # Group requests by group_id
    requests_by_group = {}
    assigned_request_ids = set()

    for req, shared_groups in filtered_requests:
        if req.id in assigned_request_ids:
            continue  # already assigned
        
        chosen_gid = min(shared_groups)  # deterministic selection
        requests_by_group.setdefault(chosen_gid, []).append(req)
        assigned_request_ids.add(req.id)

    # For each group, sort requests by username (anon last)
    for gid, requests in requests_by_group.items():
        group_name = get_group_title(gid)

        # Group requests by username (anon = None)
        reqs_by_user = {}
        for r in requests:
            key = r.username if not r.is_anonymous else None
            reqs_by_user.setdefault(key, []).append(r)

        # Sort usernames alphabetically, put None (anonymous) last
        sorted_usernames = sorted([u for u in reqs_by_user if u is not None], key=lambda x: x.lower())
        if None in reqs_by_user:
            sorted_usernames.append(None)

        # Compose message text and buttons
        message_lines = [f"<b>-- {group_name} --</b>"]
        keyboard_buttons = []

        for username in sorted_usernames:
            display_name = "Anonymous" if username is None else username
            for r in reqs_by_user[username]:
                prayed_users = all_prayed.get(r.id, set())
                prayed_mark = " ✔️" if user_id in prayed_users else ""
                keyboard_buttons.append([InlineKeyboardButton(f"{display_name}: {r.text}{prayed_mark}", callback_data=f'public_view_{r.id}')])

        message_text = "\n".join(message_lines)

        if update.message:
            await update.message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons),
                parse_mode=ParseMode.HTML
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons),
                parse_mode=ParseMode.HTML
            )


async def handle_public_request_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = query.data.split('_', 2)[2]
    req = get_request_by_rid(req_id)
    joined_users = get_joined_users(req.id)
    joined = query.from_user.id in joined_users
    join_cb = f'unjoin_{req.id}' if joined else f'join_{req.id}'
    keyboard = [
        [InlineKeyboardButton('Mark as prayed', callback_data=f'pray_{req.id}')],
        [InlineKeyboardButton('Send a written prayer', callback_data=f'textpray_{req.id}')],
        [InlineKeyboardButton('Send an audio prayer', callback_data=f'audiopray_{req.id}')],
        [InlineKeyboardButton(joined and '➖ Unjoin' or '➕ Join', callback_data=join_cb)],
        [InlineKeyboardButton("Back", callback_data="public_back_to_list")],
    ]
    await query.edit_message_text(
        f'<b>Prayer Request:</b> {req.text}\n',
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_request_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get the username of person that prayed
    query = update.callback_query
    await query.answer()

    if query.data == "public_back_to_list":
        return await request_list_command(update, context)

    action, req_id = query.data.split('_', 1)
    req = get_request_by_rid(req_id)
    user_id = query.from_user.id
    username = query.from_user.username or f"user_{user_id}"

    if not req:
        await query.edit_message_text("⚠️ This prayer request no longer exists.")
        return

    elif action == 'pray':
        mark_prayed(user_id, req.id)

        message = f'🙏 {username} has prayed for your request:\n{req.text}'
        await context.bot.send_message(chat_id=req.user_id, text=message)

        notify = f'🙏 {username} has prayed for a request you joined: {req.text}'
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

    username = update.effective_user.username or f"user_{update.effective_user.id}"
    
    req_id = context.user_data.pop('praying_req', None)
    if req_id:
        req = get_request_by_rid(req_id)
        message = (
            f'✍️ {username} has sent a written prayer:\n'
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
    username = update.effective_user.username or f"user_{update.effective_user.id}"

    req_id = context.user_data.pop('praying_req', None)
    if req_id and update.message.voice:
        req = get_request_by_rid(req_id)
        caption = f'🎤 {username} sent an audio prayer\n<b>Request:</b> {req.text}'
        await context.bot.send_voice(
            chat_id=req.user_id,
            voice=update.message.voice.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML
        )
        await update.message.reply_text('✅ Your audio prayer was sent.')
    context.user_data.clear()
    return ConversationHandler.END
