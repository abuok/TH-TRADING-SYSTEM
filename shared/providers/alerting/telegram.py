import os
import httpx
import logging

logger = logging.getLogger("TelegramProvider")


class TelegramProvider:
    """
    Adapter for Telegram Bot API.
    Required env vars: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    """

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = (
            f"https://api.telegram.org/bot{self.token}/sendMessage"
            if self.token
            else None
        )

    def send_message(self, text: str) -> bool:
        """Synchronous wrapper left for backward compatibility in non-async contexts."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If we're already in a loop, we shouldn't block it.
            # We schedule the async version as a fire-and-forget task.
            loop.create_task(self.send_message_async(text))
            return True
        else:
            return asyncio.run(self.send_message_async(text))

    async def send_message_async(self, text: str) -> bool:
        if not self.api_url or not self.chat_id:
            logger.warning(
                "TelegramProvider: Credentials missing. Skipping notification."
            )
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=5.0,
                )
                response.raise_for_status()
                return True
        except httpx.TimeoutException:
            logger.error("TelegramProvider: Request timed out")
            return False
        except httpx.HTTPStatusError as e:
            logger.error(
                f"TelegramProvider: HTTP error {e.response.status_code} - {e.response.text}"
            )
            return False
        except Exception as e:
            logger.error(f"TelegramProvider: Unexpected error - {e}")
            return False
