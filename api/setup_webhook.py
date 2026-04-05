import os
import json
import requests
from http.server import BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SETUP_SECRET = os.getenv("SETUP_SECRET", "")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if SETUP_SECRET:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {SETUP_SECRET}":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Unauthorized")
                return

        if not BOT_TOKEN:
            self._respond(400, {"ok": False, "error": "BOT_TOKEN env var is not set"})
            return

        if not WEBHOOK_URL:
            self._respond(400, {"ok": False, "error": "WEBHOOK_URL env var is not set"})
            return

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        try:
            response = requests.post(url, json={"url": WEBHOOK_URL}, timeout=10)
            self._respond(200, response.json())
        except requests.RequestException as e:
            self._respond(502, {"ok": False, "error": f"Failed to reach Telegram API: {e}"})

    def _respond(self, status: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass
