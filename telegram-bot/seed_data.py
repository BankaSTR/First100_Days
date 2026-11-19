"""Repeatable catalogue import. Fictional profiles are opt-in and never message Telegram."""
import argparse
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlparse

from config import ROOT, load_env
from store import Store

DEMO = (
    ("Саша", "16–17 лет", "Ульяновск", "Подготовиться к выпуску", "Участие в программе", "Хочу записаться на занятия и составить план на первые недели после выпуска.", "new"),
    ("Даша", "18 лет и старше", "Димитровград", "Найти работу", "Резюме и собеседование", "Первой работы ещё не было. Нужна помощь с резюме и рассказом о себе на собеседовании.", "in_progress"),
    ("Максим", "16–17 лет", "Ульяновск", "Разобраться с бытом", "Бюджет и бытовые вопросы", "Хочу научиться распределять деньги на еду, проезд и накопления на месяц.", "new"),
    ("Лера", "18 лет и старше", "Инза", "Найти работу", "Поиск работы", "Ищу первую работу с обучением. Хочу понять, какие вопросы задать работодателю.", "in_progress"),
    ("Илья", "14–15 лет", "Ульяновск", "Подготовиться к выпуску", "Участие в программе", "Интересны занятия про самостоятельную жизнь. Хочу узнать, когда будет следующая группа.", "new"),
    ("Соня", "16–17 лет", "Барыш", "Разобраться с бытом", "Бюджет и бытовые вопросы", "Потренировалась читать учебную квитанцию. Хочу проверить, правильно ли посчитала расходы.", "done"),
    ("Никита", "18 лет и старше", "Ульяновск", "Найти работу", "Поиск работы", "Хочу выбрать между работой в магазине и пиццерии. Нужна помощь со сравнением условий.", "new"),
    ("Полина", "16–17 лет", "Димитровград", "Подготовиться к выпуску", "Резюме и собеседование", "Составила учебное резюме. Хочу потренироваться отвечать на вопросы о сильных сторонах.", "in_progress"),
    ("Артём", "18 лет и старше", "Ульяновск", "Разобраться с бытом", "Бюджет и бытовые вопросы", "Составил месячный бюджет вместе со специалистом. Хочу закрепить привычку записывать расходы.", "done"),
    ("Маша", "16–17 лет", "Новоульяновск", "Пока хочу узнать о программе", "Другой вопрос", "Можно ли сначала познакомиться с координатором и обсудить личную цель на 100 дней?", "new"),
)


def seed(store, with_demo=False, catalogue=None):
    catalogue = catalogue or json.loads((ROOT / "catalogue.json").read_text(encoding="utf-8"))
    keys = [item["key"] for item in catalogue["companies"]]
    if len(keys) != len(set(keys)):
        raise ValueError("Повторяющиеся ключи организаций")
    for item in catalogue["companies"]:
        parsed = urlparse(item["source_url"])
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Источник должен быть HTTPS-ссылкой")
    before = store.db.total_changes
    now = int(time.time())
    with store.transaction():
        for item in catalogue["companies"]:
            member_key = "catalogue_member:" + item["key"]
            mapping = store.one("SELECT value FROM meta WHERE key=?", (member_key,))
            if mapping:
                uid = int(mapping[0])
            else:
                uid = min(-2000, store.one("SELECT COALESCE(MIN(id),0)-1 FROM members")[0])
                store.execute("INSERT INTO members(id,role,company,contact,employer_city,employer_status,origin,source_url,created_at) VALUES (?,'employer',?,? ,?,'catalog','catalog',?,?)",
                              (uid, item["company"], "Представитель пока не подключён", item["city"], item["source_url"], now))
                store.execute("INSERT INTO meta(key,value) VALUES (?,?)", (member_key, str(uid)))
            store.execute("INSERT OR IGNORE INTO vacancies(employer_id,company,title,city,schedule,pay,age,description,status,created_at,source_url,source_checked_on,seed_key) VALUES (?,?,?,?,?,?,?,?,'catalog',?,?,?,?)",
                          (uid, item["company"], item["title"], item["city"], item["schedule"], item["pay"], "18 лет и старше", item["description"], now, item["source_url"], catalogue["collected_on"], "catalogue:" + item["key"]))
        if with_demo:
            for index, (name, age, city, goal, topic, body, status) in enumerate(DEMO, 1):
                key = f"demo:participant:{index}"
                mapping = store.one("SELECT value FROM meta WHERE key=?", (key,))
                if mapping:
                    uid = int(mapping[0])
                else:
                    uid = min(-1000, store.one("SELECT COALESCE(MIN(id),0)-1 FROM members")[0])
                    store.execute("INSERT INTO members(id,name,age,city,goal,origin,created_at) VALUES (?,?,?,?,?,'demo',?)", (uid, name, age, city, goal, now))
                    store.execute("INSERT INTO meta(key,value) VALUES (?,?)", (key, str(uid)))
                snapshot = {"name": name, "age": age, "city": city, "company": "", "contact": "", "role": "participant"}
                response = "Вместе со специалистом разобрали задачу и составили следующий шаг." if status == "done" else ""
                store.execute("INSERT OR IGNORE INTO applications(user_id,topic,body,snapshot,status,response,created_at,is_demo,seed_key) VALUES (?,?,?,?,?,?,?,1,?)",
                              (uid, topic, body, json.dumps(snapshot, ensure_ascii=False), status, response, now, f"demo:application:{index}"))
    return store.db.total_changes - before


def main():
    parser = argparse.ArgumentParser(description="Добавить каталог вакансий и учебные записи без рассылки сообщений")
    parser.add_argument("--with-demo", action="store_true", help="Добавить 10 вымышленных участников и заявок")
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    load_env(ROOT / ".env")
    path = args.database or Path(os.getenv("BOT_DATABASE", str(ROOT / "data" / "bot.sqlite3")))
    if not path.is_absolute():
        path = ROOT / path
    if path.exists():
        backups = path.parent / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f"before-seed-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3"
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        print("Резервная копия сохранена в data/backups.")
    store = Store(path)
    try:
        changes = seed(store, args.with_demo)
        print(f"Готово. Новых записей: {changes}. Повторный запуск не создаёт дубликаты.")
        for table, condition, title in (
            ("members", "origin='catalog'", "Организации из открытых источников"),
            ("vacancies", "seed_key LIKE 'catalogue:%'", "Карточки вакансий"),
            ("members", "origin='demo'", "Учебные участники"),
            ("applications", "is_demo=1", "Учебные заявки"),
        ):
            print(f"{title}: {store.one(f'SELECT COUNT(*) FROM {table} WHERE {condition}')[0]}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
