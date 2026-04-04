# LOL-Prayer-Bot
Telegram prayer bot 

### Run locally
- `pip install --user -r requirements.txt`
- `python main.py`

### Deployment on Vercel (free)

1. Install the [Vercel CLI](https://vercel.com/docs/cli): `npm i -g vercel`
2. Deploy: `vercel --prod`
3. Set the required environment variables in the Vercel dashboard (or via `vercel env add`):
   - `BOT_TOKEN` – your Telegram bot token
   - `BOT_ID` – your bot's Telegram user ID
   - `CRON_SECRET` – a secret string to protect the daily reminder endpoint (optional but recommended)
4. Register the webhook with Telegram so updates are forwarded to your deployment:
   ```
   curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<your-vercel-domain>/api/webhook"
   ```
5. The daily reminder cron runs at **01:00 UTC** (09:00 SGT / UTC+8).

> **Note:** Vercel's serverless filesystem is ephemeral. The SQLite database (`prayerbot.db`) is stored in `/tmp` and will be reset between cold starts. For persistent storage across deployments, consider migrating to an external database such as [Vercel Postgres](https://vercel.com/docs/storage/vercel-postgres) or [PlanetScale](https://planetscale.com/).

> **Note:** Multi-step conversations (e.g. `/add_request`) require in-memory state that is not shared across serverless invocations. Each update is handled by an independent function instance, so conversation flows will work within a single session but may not resume after a cold start.

### Deployment on Pythonanywhere
- create new console
- `chmod +x deploy.sh`
- `./deploy.sh`
