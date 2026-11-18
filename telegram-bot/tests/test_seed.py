import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from config import Config, ROOT
from seed_data import seed
from service import Bot
from store import SCHEMA, Store


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "bot.sqlite3"
        self.s = Store(self.path)
        self.bot = Bot(self.s, Config("unused", frozenset({100}), self.path))
        for uid in (1, 100):
            self.s.execute("INSERT INTO members(id,name,age,city,consent_at,created_at) VALUES (?,?,?,'Ульяновск',1,?)", (uid, "Настоящий пользователь", "18 лет и старше", int(time.time())))

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def payloads(self):
        return [json.loads(row[0]) for row in self.s.all("SELECT payload FROM outbox WHERE method='sendMessage' ORDER BY id")]

    def test_repeat_import_preserves_real_data_and_processed_demo(self):
        self.s.execute("INSERT INTO applications(user_id,topic,body,snapshot,created_at) VALUES (1,'Вопрос','Настоящая заявка','{}',1)")
        seed(self.s, True)
        demo = self.s.one("SELECT id FROM applications WHERE is_demo=1")[0]
        self.s.execute("UPDATE applications SET status='done',response='Ответ сохранён' WHERE id=?", (demo,))
        self.assertEqual(seed(self.s, True), 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM members WHERE origin='catalog'")[0], 10)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM vacancies")[0], 10)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM members WHERE origin='demo'")[0], 10)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications WHERE is_demo=1")[0], 10)
        self.assertEqual(self.s.one("SELECT body FROM applications WHERE is_demo=0")[0], "Настоящая заявка")
        self.assertEqual(self.s.one("SELECT response FROM applications WHERE id=?", (demo,))[0], "Ответ сохранён")
        self.assertEqual(len(self.payloads()), 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM members WHERE origin='demo' AND consent_at IS NOT NULL")[0], 0)

    def test_demo_is_opt_in(self):
        seed(self.s)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM members WHERE origin='demo'")[0], 0)

    def test_catalogue_reply_is_explicit_and_goes_only_to_coordinator(self):
        seed(self.s, True)
        job_id = self.s.one("SELECT id FROM vacancies LIMIT 1")[0]
        self.bot.begin_apply(1, job_id)
        self.bot.input(1, "Хочу обсудить первую работу и график.")
        self.assertIn("получит координатор", self.payloads()[-1]["text"])
        self.s.execute("DELETE FROM outbox")
        self.bot.submit(1, self.bot.flow(1))
        self.assertEqual({item["chat_id"] for item in self.payloads()}, {1, 100})
        self.assertIn("поможет связаться", self.payloads()[0]["text"])
        app = self.s.one("SELECT id FROM applications WHERE is_demo=0")[0]
        self.bot.application(100, app)
        self.assertIn("Компания пока не подключена", self.payloads()[-1]["text"])
        self.bot.management(100, "done", app)
        self.assertEqual(self.s.one("SELECT status FROM applications WHERE id=?", (app,))[0], "done")

    def test_unverified_age_cannot_be_bypassed_by_callback(self):
        seed(self.s)
        self.s.execute("UPDATE members SET age='16–17 лет' WHERE id=1")
        job = self.s.one("SELECT id FROM vacancies LIMIT 1")[0]
        self.assertIsNone(self.bot.eligible_job(1, job))
        self.bot.begin_apply(1, job)
        self.assertIsNone(self.bot.flow(1))

    def test_private_demo_cards_and_no_synthetic_recipients(self):
        seed(self.s, True)
        uid = self.s.one("SELECT id FROM members WHERE origin='demo'")[0]
        self.bot.action(1, f"participant:{uid}")
        self.assertIn("доступно координатору", self.payloads()[-1]["text"])
        self.bot.action(100, f"participant:{uid}")
        self.assertIn("вымышленные данные", self.payloads()[-1]["text"])
        app = self.s.one("SELECT id FROM applications WHERE is_demo=1 AND status='new'")[0]
        self.bot.application(100, app)
        self.assertIn("Учебный пример", self.payloads()[-1]["text"])
        self.bot.submit_admin(100, "reply", {"id": app, "body": "Учебный ответ"})
        self.assertIn("Учебный ответ сохранён", self.payloads()[-1]["text"])
        self.assertTrue(all(item["chat_id"] > 0 for item in self.payloads()))

    def test_all_catalogue_sections_paginate_and_sources_open_as_urls(self):
        seed(self.s, True)
        for kind in ("employers", "vacancies", "participants", "applications"):
            self.bot.queue(100, kind, 0)
            keyboard = self.payloads()[-1]["reply_markup"]["inline_keyboard"]
            self.assertTrue(any(item.get("callback_data") == f"queue:{kind}:1" for row in keyboard for item in row))
            self.bot.queue(100, kind, 1)
            self.assertNotIn("пока пусто", self.payloads()[-1]["text"])
        uid = self.s.one("SELECT id FROM members WHERE origin='catalog'")[0]
        self.bot.action(100, f"employer:{uid}")
        self.assertIn("Из открытых источников", self.payloads()[-1]["text"])
        self.assertFalse(any("approve_employer" in item.get("callback_data", "") for row in self.payloads()[-1]["reply_markup"]["inline_keyboard"] for item in row))
        job = self.s.one("SELECT id FROM vacancies LIMIT 1")[0]
        self.bot.job(1, job)
        self.assertTrue(any(item.get("url", "").startswith("https://") for row in self.payloads()[-1]["reply_markup"]["inline_keyboard"] for item in row))

    def test_migration_keeps_legacy_database_and_is_repeatable(self):
        legacy = Path(self.temp.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO members(id,name,created_at) VALUES (7,'Существующая анкета',1)")
            db.commit()
        for _ in range(2):
            migrated = Store(legacy)
            self.assertEqual(migrated.one("SELECT name,origin FROM members WHERE id=7")["name"], "Существующая анкета")
            seed(migrated)
            migrated.close()

    def test_cli_creates_restorable_backup_before_import(self):
        result = subprocess.run([sys.executable, str(ROOT / "seed_data.py"), "--database", str(self.path), "--with-demo"], capture_output=True, text=True, encoding="utf-8", env=__import__("os").environ | {"PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list((self.path.parent / "backups").glob("*.sqlite3"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM members").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
