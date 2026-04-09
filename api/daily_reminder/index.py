import sys
import os
import html
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException

import requests as http_requests
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode

from database import init_db, get_all_user_ids, get_all_prayer_requests, get_user_groups

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CRON_SECRET = os.getenv("CRON_SECRET", "")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID", "")

VOTD_URL = "https://beta.ourmanna.com/api/v1/get?format=json&order=daily"

app = FastAPI()


# ======================
# Helpers
# ======================

def _get_votd() -> str:
    try:
        response = http_requests.get(
            VOTD_URL,
            headers={"accept": "application/json"},
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        details = data.get("verse", {}).get("details", {})
        verse = str(details.get("text", "")).strip()
        reference = str(details.get("reference", "")).strip()

        if not verse:
            raise ValueError("VOTD response did not include verse text")

        # Escape dynamic text because message is sent with ParseMode.HTML.
        safe_verse = html.escape(verse)
        safe_reference = html.escape(reference) if reference else "Unknown Reference"
        return f"{safe_verse} - <i>{safe_reference}</i>"
    except Exception as exc:
        print(f"Failed to fetch VOTD: {exc}")
        return "Stay faithful and trust in the Lord today!"


async def _send_daily_reminders() -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN environment variable")

    init_db()

    bot = Bot(token=BOT_TOKEN)
    user_ids = get_all_user_ids()
    all_requests = get_all_prayer_requests()
    verse_of_the_day = _get_votd()
    sent_count = 0
    failed_count = 0
    failures = []

    print(
        "Daily reminder run starting:",
        f"users={len(user_ids)}",
        f"requests={len(all_requests)}",
    )

    async with bot:
        for uid in user_ids:
            if uid <= 0:
                continue

            viewer_groups = get_user_groups(uid)
            visible_requests = []

            for req in all_requests:
                if req.user_id == uid:
                    continue

                creator_groups = get_user_groups(req.user_id)
                if viewer_groups & creator_groups:
                    visible_requests.append(req)

            if visible_requests:
                request_lines = "\n".join(
                    f"• {html.escape(req.text)}" for req in visible_requests
                )
                requests_section = (
                    f"📋 <b>Prayer Requests ({len(visible_requests)}):</b>\n"
                    f"{request_lines}\n\n"
                    "Use /request_list to view and interact with these requests."
                )
            else:
                requests_section = "There are no prayer requests from others today."

            daily_text = (
                "<b>-- Daily Prayer Reminder --</b>\n\n"
                f"{verse_of_the_day}\n\n"
                f"{requests_section}"
            )

            try:
                await bot.send_message(
                    chat_id=uid,
                    text=daily_text,
                    parse_mode=ParseMode.HTML
                )
                sent_count += 1
            except Exception as e:
                failed_count += 1
                failures.append(f"{uid}: {e}")
                print(f"Failed to send to {uid}: {e}")

    summary = {
        "users_found": len(user_ids),
        "requests_found": len(all_requests),
        "sent": sent_count,
        "failed": failed_count,
    }
    if failures:
        summary["failure_samples"] = failures[:3]

    print(f"Daily reminder run complete: {summary}")
    return summary


# ======================
# Endpoint
# ======================

@app.get("/api/daily_reminder")
async def daily_reminder(request: Request):
    print(
        "Daily reminder endpoint invoked:",
        f"ua={request.headers.get('user-agent', '')}",
        f"x-vercel-cron={request.headers.get('x-vercel-cron', '')}",
    )

    # 🔐 Optional security check
    if CRON_SECRET:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {CRON_SECRET}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        summary = await _send_daily_reminders()
        return {"status": "ok", **summary}
    except HTTPException:
        raise
    except Exception as exc:
        if BOT_TOKEN and CREATOR_CHAT_ID:
            try:
                creator_id = int(CREATOR_CHAT_ID)
            except ValueError:
                print(f"CREATOR_CHAT_ID is not a valid integer: {CREATOR_CHAT_ID!r}")
                creator_id = None
            if creator_id is not None:
                try:
                    async with Bot(token=BOT_TOKEN) as bot:
                        await bot.send_message(
                            chat_id=creator_id,
                            text=f"⚠️ Daily reminder failed to send today.\n\nError: {exc}",
                        )
                except Exception as notify_exc:
                    print(f"Failed to notify creator: {notify_exc}")
        raise HTTPException(status_code=500, detail=f"Daily reminder failed: {exc}") from exc