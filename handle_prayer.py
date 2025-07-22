# handle_prayer.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from handle_request import prayer_requests
from state import (
    PRAY_TEXT,
    PRAY_AUDIO, 
    group_members,
    user_groups,
    group_titles,
)


async def request_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    viewer_groups = user_groups.get(user_id, set())

    public_requests = []
    group_requests_by_chat = {}


    for r in prayer_requests.values():
        if r.user_id == user_id:
            continue

        if r.visibility == "public":
            public_requests.append(r)

        elif r.visibility == "group":
            creator_groups = user_groups.get(r.user_id, set())
            shared_groups = viewer_groups & creator_groups
            for gid in shared_groups:
                group_requests_by_chat.setdefault(gid, []).append(r)

    if not public_requests and not group_requests_by_chat:
        await update.message.reply_text('No prayer requests from others are available.')
        return

    # Build message
    lines = ['🙏 <b>Prayer Requests</b>:\n']

    # Public Section
    if public_requests:
        lines.append('<b>-- Public --</b>')
        for r in public_requests:
            name = "Anonymous" if r.is_anonymous else r.username
            prayed = " (✔️ Prayed)" if user_id in r.prayed_users else ""
            lines.append(f'• <b>{name}</b>: {r.text}')
            lines.append(f'• <b>{name}</b>: {r.text}{prayed}')
        lines.append("")  # Add spacing

    # Group Sections
    for gid, requests in group_requests_by_chat.items():
        title = group_titles.get(gid, f"Group {gid}")
        lines.append(f'<b>-- {title} --</b>')
        for r in requests:
            name = "Anonymous" if r.is_anonymous else r.username
            prayed = " (✔️ Prayed)" if user_id in r.prayed_users else ""
            lines.append(f'• <b>{name}</b>: {r.text}{prayed}')
        lines.append("")  # Add spacing
    
    while lines and lines[-1] == "":
        lines.pop()

    # Send public requests individually
    for r in public_requests:
        name = "Anonymous" if r.is_anonymous else r.username
        prayed = " ✔️" if user_id in r.prayed_users else ""
        button_text = f"{r.text}{prayed}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(button_text, callback_data=f'public_view_{r.id}')]
        ])
        await update.message.reply_text(
            f"{name}:",  # plain text name
            reply_markup=keyboard
        )

    # For group requests (same format)
    for gid, requests in group_requests_by_chat.items():
        title = group_titles.get(gid, f"Group {gid}")
        await update.message.reply_text(f'<b>-- {title} --</b>', parse_mode=ParseMode.HTML)
        for r in requests:
            name = "Anonymous" if r.is_anonymous else r.username
            prayed = " ✔️" if user_id in r.prayed_users else ""
            button_text = f"{r.text}{prayed}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(button_text, callback_data=f'public_view_{r.id}')]
            ])
            await update.message.reply_text(
                f"{name}:",  # plain text name
                reply_markup=keyboard
            )

async def handle_public_request_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = query.data.split('_', 2)[2]
    req = prayer_requests.get(req_id)
    joined = query.from_user.id in req.joined_users
    join_cb = f'unjoin_{req.id}' if joined else f'join_{req.id}'
    keyboard = [
        [InlineKeyboardButton('Mark as prayed', callback_data=f'pray_{req.id}')],
        [InlineKeyboardButton('Send a written prayer', callback_data=f'textpray_{req.id}')],
        [InlineKeyboardButton('Send an audio prayer', callback_data=f'audiopray_{req.id}')],
        [InlineKeyboardButton(joined and '➖ Unjoin' or '➕ Join', callback_data=join_cb)],
    ]
    await query.edit_message_text(
        f'*Prayer Request: *{req.text}',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_request_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, req_id = query.data.split('_', 1)
    req = prayer_requests.get(req_id)
    user_id = query.from_user.id
    if action == 'pray':
        req.prayed_users.add(user_id)

        message = f'Someone prayed for your request: {req.text}'
        await context.bot.send_message(chat_id=req.user_id, text=message)

        notify = f'Someone prayed for a request you joined: {req.text}'
        for uid in req.joined_users:
            if uid != user_id:
                await context.bot.send_message(chat_id=uid, text=notify)
        await query.edit_message_text('✅ Marked as prayed.')

    elif action in ('join', 'unjoin'):
        (req.joined_users.add if action == 'join' else req.joined_users.discard)(user_id)
        await query.edit_message_text(action == 'join' and 'Joined' or 'Unjoined')

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
        req = prayer_requests[req_id]
        message = (
            f'✍️ Someone sent a written prayer\n'
            f'*Request: *{req.text}\n'
            f'*Prayer: *{update.message.text}'
        )
        await context.bot.send_message(chat_id=req.user_id, text=message, parse_mode='Markdown')
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
        req = prayer_requests[req_id]
        caption = f'🎤 Someone sent an audio prayer\nRequest: {req.text}'
        await context.bot.send_voice(chat_id=req.user_id, voice=update.message.voice.file_id, caption=caption)
        await update.message.reply_text('✅ Your audio prayer was sent.')
    context.user_data.clear()
    return ConversationHandler.END
