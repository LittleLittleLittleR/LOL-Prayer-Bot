"""Tests for the /api/daily_reminder endpoint."""
import sys
import os

# Ensure repo root and the daily_reminder module are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "daily_reminder"))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from state import PrayerRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(req_id, user_id, text, is_anonymous=False):
    return PrayerRequest(
        id=req_id,
        user_id=user_id,
        username=f"user_{user_id}",
        text=text,
        is_anonymous=is_anonymous,
    )


def _mock_votd_response(verse="Be strong.", reference="Josh 1:9"):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "verse": {"details": {"text": verse, "reference": reference}}
    }
    return mock_resp


# ---------------------------------------------------------------------------
# _get_votd unit tests
# ---------------------------------------------------------------------------

class TestGetVotd:
    def test_returns_formatted_verse(self):
        import index as dr
        with patch("index.http_requests.get", return_value=_mock_votd_response()) as mock_get:
            result = dr._get_votd()
        mock_get.assert_called_once()
        assert "Be strong." in result
        assert "Josh 1:9" in result
        assert "<i>" in result

    def test_fallback_on_network_error(self):
        import index as dr
        with patch("index.http_requests.get", side_effect=Exception("timeout")):
            result = dr._get_votd()
        assert result == "Stay faithful and trust in the Lord today!"

    def test_fallback_on_empty_verse(self):
        import index as dr
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"verse": {"details": {"text": "", "reference": ""}}}
        with patch("index.http_requests.get", return_value=mock_resp):
            result = dr._get_votd()
        assert result == "Stay faithful and trust in the Lord today!"

    def test_html_special_chars_are_escaped(self):
        import index as dr
        verse = "Trust <Him> & 'believe'."
        with patch("index.http_requests.get", return_value=_mock_votd_response(verse=verse)):
            result = dr._get_votd()
        assert "<Him>" not in result
        assert "&lt;Him&gt;" in result


# ---------------------------------------------------------------------------
# _send_daily_reminders unit tests
# ---------------------------------------------------------------------------

class TestSendDailyReminders:
    @pytest.mark.asyncio
    async def test_sends_message_with_prayer_list(self):
        import index as dr

        user_a, user_b = 111, 222
        req = _make_request("req1", user_b, "Pray for my family")

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.init_db"),
            patch("index.get_all_user_ids", return_value=[user_a, user_b]),
            patch("index.get_all_prayer_requests", return_value=[req]),
            patch("index.get_user_groups", side_effect=lambda uid: {1}),
            patch("index.http_requests.get", return_value=_mock_votd_response()),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            with patch("index.Bot", return_value=mock_bot):
                summary = await dr._send_daily_reminders()

        # user_a should receive a message containing the prayer request text
        calls = mock_bot.send_message.call_args_list
        user_a_calls = [c for c in calls if c.kwargs.get("chat_id") == user_a]
        assert len(user_a_calls) == 1
        text_sent = user_a_calls[0].kwargs["text"]
        assert "Pray for my family" in text_sent
        assert "Daily Prayer Reminder" in text_sent

        assert summary["sent"] == 2
        assert summary["failed"] == 0

    @pytest.mark.asyncio
    async def test_no_cross_group_requests_shown(self):
        """Users in different groups should not see each other's requests."""
        import index as dr

        user_a, user_b = 111, 222
        req = _make_request("req1", user_b, "Secret request")

        def groups_by_user(uid):
            return {10} if uid == user_a else {20}  # different groups

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.init_db"),
            patch("index.get_all_user_ids", return_value=[user_a, user_b]),
            patch("index.get_all_prayer_requests", return_value=[req]),
            patch("index.get_user_groups", side_effect=groups_by_user),
            patch("index.http_requests.get", return_value=_mock_votd_response()),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            with patch("index.Bot", return_value=mock_bot):
                await dr._send_daily_reminders()

        calls = mock_bot.send_message.call_args_list
        user_a_calls = [c for c in calls if c.kwargs.get("chat_id") == user_a]
        assert len(user_a_calls) == 1
        text_sent = user_a_calls[0].kwargs["text"]
        # user_a is in a different group so should NOT see user_b's request
        assert "Secret request" not in text_sent
        assert "no prayer requests" in text_sent

    @pytest.mark.asyncio
    async def test_skips_negative_user_ids(self):
        """Group chat IDs (negative) must be skipped."""
        import index as dr

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.init_db"),
            patch("index.get_all_user_ids", return_value=[-100123456, 0]),
            patch("index.get_all_prayer_requests", return_value=[]),
            patch("index.get_user_groups", return_value=set()),
            patch("index.http_requests.get", return_value=_mock_votd_response()),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            with patch("index.Bot", return_value=mock_bot):
                summary = await dr._send_daily_reminders()

        mock_bot.send_message.assert_not_called()
        assert summary["sent"] == 0

    @pytest.mark.asyncio
    async def test_failed_send_counted(self):
        """Failed bot.send_message calls are counted in the summary."""
        import index as dr

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.init_db"),
            patch("index.get_all_user_ids", return_value=[111]),
            patch("index.get_all_prayer_requests", return_value=[]),
            patch("index.get_user_groups", return_value=set()),
            patch("index.http_requests.get", return_value=_mock_votd_response()),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            mock_bot.send_message = AsyncMock(side_effect=Exception("Forbidden"))
            with patch("index.Bot", return_value=mock_bot):
                summary = await dr._send_daily_reminders()

        assert summary["sent"] == 0
        assert summary["failed"] == 1

    @pytest.mark.asyncio
    async def test_raises_without_bot_token(self):
        import index as dr

        with patch.dict(os.environ, {"BOT_TOKEN": ""}):
            with patch("index.BOT_TOKEN", ""):
                with pytest.raises(RuntimeError, match="Missing BOT_TOKEN"):
                    await dr._send_daily_reminders()


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------
class TestDailyReminderEndpoint:
    @pytest.mark.asyncio
    async def test_returns_ok_on_success(self):
        import index as dr

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.init_db"),
            patch("index.get_all_user_ids", return_value=[111]),
            patch("index.get_all_prayer_requests", return_value=[]),
            patch("index.get_user_groups", return_value=set()),
            patch("index.http_requests.get", return_value=_mock_votd_response()),
            patch.dict(os.environ, {"CRON_SECRET": ""}),
            patch("index.CRON_SECRET", ""),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            with patch("index.Bot", return_value=mock_bot):
                async with AsyncClient(
                    transport=ASGITransport(app=dr.app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/daily_reminder")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "sent" in body
        assert "failed" in body

    @pytest.mark.asyncio
    async def test_returns_401_with_wrong_secret(self):
        import index as dr

        with (
            patch("index.CRON_SECRET", "mysecret"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=dr.app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/daily_reminder",
                    headers={"Authorization": "Bearer wrongsecret"},
                )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_accepts_correct_secret(self):
        import index as dr

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.init_db"),
            patch("index.get_all_user_ids", return_value=[]),
            patch("index.get_all_prayer_requests", return_value=[]),
            patch("index.http_requests.get", return_value=_mock_votd_response()),
            patch("index.CRON_SECRET", "mysecret"),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            with patch("index.Bot", return_value=mock_bot):
                async with AsyncClient(
                    transport=ASGITransport(app=dr.app), base_url="http://test"
                ) as client:
                    response = await client.get(
                        "/api/daily_reminder",
                        headers={"Authorization": "Bearer mysecret"},
                    )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_notifies_creator_on_failure(self):
        """When _send_daily_reminders raises, a Telegram message is sent to the creator."""
        import index as dr

        with (
            patch("index.BOT_TOKEN", "fake-token"),
            patch("index.CREATOR_CHAT_ID", "99999"),
            patch("index.CRON_SECRET", ""),
            patch("index._send_daily_reminders", new=AsyncMock(side_effect=RuntimeError("DB error"))),
        ):
            mock_bot = AsyncMock()
            mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
            mock_bot.__aexit__ = AsyncMock(return_value=False)
            with patch("index.Bot", return_value=mock_bot):
                async with AsyncClient(
                    transport=ASGITransport(app=dr.app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/daily_reminder")

        assert response.status_code == 500
        mock_bot.send_message.assert_awaited_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 99999
        assert "DB error" in call_kwargs["text"]
