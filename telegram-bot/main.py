"""Run with `python main.py`. A persistent worker hosts the Telegram conversation."""
from contextlib import contextmanager
import argparse
import logging
import os
from pathlib import Path
import signal
import threading
import time

from config import Config
from service import Bot
from store import Store
from telegram import Telegram, TelegramError

log = logging.getLogger("first100.bot")


@contextmanager
def single_instance(database: Path):
    database.parent.mkdir(parents=True, exist_ok=True)
    with database.with_suffix(".lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Бот с этой базой уже запущен. Остановите второй процесс.") from None
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run(config, check=False):
    api = Telegram(config.token)
    identity = api.call("getMe")
    log.info("Подключён @%s", identity["username"])
    webhook = api.call("getWebhookInfo")
    if webhook.get("url"):
        raise RuntimeError("У бота уже настроен webhook. Для этого проекта используйте отдельного бота или самостоятельно отключите прежний webhook.")
    if check:
        log.info("Токен верный, бот готов к long polling.")
        return
    with single_instance(config.database):
        store = Store(config.database)
        try:
            bot = Bot(store, config)
            api.call("setMyCommands", {"commands": [
                {"command": "start", "description": "Начать и выбрать роль"},
                {"command": "menu", "description": "Главное меню"},
                {"command": "cancel", "description": "Отменить заполнение"},
                {"command": "help", "description": "Как пользоваться ботом"},
                {"command": "privacy", "description": "Как используются данные"},
                {"command": "id", "description": "Мой Telegram ID"},
            ]})
            api.call("setMyDescription", {"description": "Первые 100 дней — подготовка к самостоятельной жизни. Регистрация участников и работодателей, заявки на помощь, проверенные вакансии и отклики. Нажми «Начать»."})
            api.call("setMyShortDescription", {"short_description": "Регистрация, заявки на помощь и первая работа. Программа «Первые 100 дней»."})
            stopping = threading.Event()
            signal.signal(signal.SIGINT, lambda *_: stopping.set())
            signal.signal(signal.SIGTERM, lambda *_: stopping.set())
            log.info("Бот запущен. Для остановки нажмите Ctrl+C.")
            failures = 0
            while not stopping.is_set():
                try:
                    api.flush(store)
                    updates = api.call("getUpdates", {"offset": store.offset(), "timeout": 10, "limit": 30, "allowed_updates": ["message", "callback_query"]})
                    for update in updates:
                        if stopping.is_set():
                            break
                        bot.process(update)
                        api.flush(store)
                    failures = 0
                except TelegramError as error:
                    if error.code in (401, 409):
                        raise RuntimeError("Токен отозван или бот уже запущен в другом месте. Проверьте единственный экземпляр бота.") from None
                    failures += 1
                    log.warning("Telegram временно недоступен, повторяем подключение. Код %s", error.code)
                    stopping.wait(max(error.retry_after, min(30, 2 ** min(failures, 5))))
                except Exception:
                    # Do not print update bodies, Telegram URLs or credentials.
                    log.error("Обработка не завершена. Изменения отменены, обновление будет повторено. Проверьте доступность базы.")
                    stopping.wait(3)
            log.info("Бот остановлен. Данные и необработанные сообщения сохранены.")
        finally:
            store.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Telegram-бот программы «Первые 100 дней»")
    parser.add_argument("--check", action="store_true", help="Проверить токен без запуска получения сообщений")
    args = parser.parse_args()
    try:
        run(Config.from_env(), args.check)
    except (ValueError, RuntimeError) as error:
        log.error("%s", error)
        return 1
    except TelegramError as error:
        log.error("Не удалось подключиться к Telegram. Код %s. Проверьте токен и интернет.", error.code)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
