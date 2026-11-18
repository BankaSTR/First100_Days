"""Small Telegram Bot API client with redacted failures and bounded retries."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramError(Exception):
    def __init__(self, code, retry_after=0):
        super().__init__(f"Telegram API error {code}")
        self.code = code
        self.retry_after = retry_after


class Telegram:
    def __init__(self, token):
        self._url = f"https://api.telegram.org/bot{token}/"

    def call(self, method, payload=None):
        data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = Request(self._url + method, data=data, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=35) as response:
                result = json.load(response)
        except HTTPError as error:
            try:
                result = json.load(error)
            except (ValueError, OSError):
                raise TelegramError(error.code) from None
        except (URLError, TimeoutError, OSError):
            raise TelegramError(503) from None
        if not result.get("ok"):
            raise TelegramError(result.get("error_code", 503), result.get("parameters", {}).get("retry_after", 0))
        return result["result"]

    def flush(self, store):
        # The API has no idempotency key for sendMessage. A crash immediately after
        # successful delivery may repeat a notification, never the application itself.
        pending = store.all("SELECT * FROM outbox WHERE status='pending' AND available_at<=? ORDER BY id LIMIT 40", (int(time.time()),))
        for item in pending:
            try:
                self.call(item["method"], json.loads(item["payload"]))
            except TelegramError as error:
                if error.code in (400, 401, 403, 404) or item["attempts"] >= 9:
                    store.execute("UPDATE outbox SET status='failed',attempts=attempts+1 WHERE id=?", (item["id"],))
                else:
                    delay = max(error.retry_after, min(300, 2 ** (item["attempts"] + 1)))
                    store.execute("UPDATE outbox SET attempts=attempts+1,available_at=? WHERE id=?", (int(time.time()) + delay, item["id"]))
                    break
            else:
                store.execute("DELETE FROM outbox WHERE id=?", (item["id"],))
