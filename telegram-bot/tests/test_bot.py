from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from config import Config
from service import Bot, FORMS
from store import Store
from telegram import Telegram, TelegramError


class BotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "bot.sqlite3"
        self.s = Store(self.path)
        self.config = Config("unused", frozenset({100}), self.path)
        self.bot = Bot(self.s, self.config)
        self.update_id = 0
        for uid in (1, 2, 3, 100):
            self.message(uid, "/start")

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def update(self, uid, value, callback=False):
        self.update_id += 1
        update = {"update_id": self.update_id}
        message = {"message_id": self.update_id, "chat": {"id": uid, "type": "private"}, "from": {"id": uid}}
        if callback:
            update["callback_query"] = {"id": str(self.update_id), "from": {"id": uid}, "message": message, "data": value}
        else:
            message["text"] = value
            update["message"] = message
        return update

    def message(self, uid, value):
        self.bot.process(self.update(uid, value))

    def action(self, uid, value):
        self.bot.process(self.update(uid, value, True))

    def choose(self, uid, value):
        nonce = self.bot.flow(uid)["nonce"]
        self.action(uid, f"f:{nonce}:{value}")

    def last(self, uid):
        payloads = [json.loads(x[0]) for x in self.s.all("SELECT payload FROM outbox WHERE method='sendMessage' ORDER BY id")]
        return next(x for x in reversed(payloads) if x["chat_id"] == uid)

    def fill(self, uid, kind, values):
        if kind in ("participant", "employer"):
            self.action(uid, "register:" + kind)
            self.choose(uid, "consent")
        elif kind != "apply":
            self.action(uid, "new:" + kind)
        for field, value in zip(FORMS[kind], values, strict=True):
            if field.options:
                self.choose(uid, str(field.options.index(value)))
            else:
                self.message(uid, value)

    def participant(self, uid=1, age="18 лет и старше", name="Саша"):
        self.fill(uid, "participant", (name, age, "Ульяновск", "Найти работу"))
        self.choose(uid, "send")

    def employer(self):
        self.fill(2, "employer", ("Книжный магазин", "Анна, управляющая", "Ульяновск"))
        self.choose(2, "send")
        revision = self.bot.member(2)["employer_consent_at"]
        self.action(100, f"approve_employer:2:{revision}")

    def vacancy(self, age="16–17 лет", approve=True):
        self.employer()
        self.fill(2, "vacancy", ("Помощник", "Ульяновск", "После учёбы, 2 часа", "350 ₽ в час", age, "Раскладывать книги, оплачиваемое обучение и оформление."))
        self.choose(2, "send")
        job_id = self.s.one("SELECT MAX(id) FROM vacancies")[0]
        if approve:
            self.action(100, f"approve_vacancy:{job_id}")
        return job_id

    def apply(self, job_id, uid=1):
        self.action(uid, f"apply:{job_id}")
        self.message(uid, "Люблю книги, умею работать с таблицами. Могу после учёбы.")
        self.choose(uid, "send")
        return self.s.one("SELECT MAX(id) FROM applications")[0]

    def test_registration_requires_consent_and_confirmation(self):
        self.action(1, "register:participant")
        self.message(1, "Имя до согласия")
        self.assertIsNone(self.bot.member(1)["consent_at"])
        self.choose(1, "consent")
        self.message(1, "Саша")
        self.choose(1, "3")
        self.message(1, "Ульяновск")
        self.choose(1, "0")
        self.assertIsNone(self.bot.member(1)["consent_at"])
        self.choose(1, "send")
        self.assertEqual(self.bot.member(1)["name"], "Саша")
        self.assertTrue(self.bot.member(1)["consent_at"])

    def test_resume_after_restart(self):
        self.action(1, "register:participant")
        self.choose(1, "consent")
        self.message(1, "Саша")
        self.s.close()
        self.s = Store(self.path)
        self.bot = Bot(self.s, self.config)
        self.message(1, "/start")
        self.assertEqual(self.bot.flow(1)["step"], 1)
        self.action(1, "resume")
        self.assertIn("возрастную", self.last(1)["text"])

    def test_back_edits_answer(self):
        self.fill(1, "participant", ("Саша", "18 лет и старше", "Ульяновск", "Найти работу"))
        self.choose(1, "back")
        self.choose(1, "back")
        self.message(1, "Казань")
        self.choose(1, "0")
        self.choose(1, "send")
        self.assertEqual(self.bot.member(1)["city"], "Казань")

    def test_cancel_requires_confirmation(self):
        self.action(1, "register:participant")
        self.message(1, "/cancel")
        self.assertIsNotNone(self.bot.flow(1))
        self.choose(1, "cancel")
        self.assertIsNone(self.bot.flow(1))

    def test_old_buttons_do_not_skip_steps(self):
        self.action(1, "register:participant")
        nonce = self.bot.flow(1)["nonce"]
        self.choose(1, "consent")
        self.action(1, f"f:{nonce}:3")
        self.assertEqual(self.bot.flow(1)["step"], 0)

    def test_request_reaches_admin_and_answer_reaches_user(self):
        self.participant()
        self.fill(1, "request", ("Участие в программе", "Хочу присоединиться к занятиям."))
        self.choose(1, "send")
        app = self.s.one("SELECT * FROM applications")
        self.assertIn("Новая заявка", self.last(100)["text"])
        self.action(100, f"reply:{app['id']}")
        self.message(100, "Расскажу о ближайшей встрече здесь.")
        self.choose(100, "send")
        self.assertIn("ближайшей встрече", self.last(1)["text"])
        self.assertEqual(self.s.one("SELECT status FROM applications")[0], "in_progress")

    def test_duplicate_update_and_confirmation_create_one_request(self):
        self.participant()
        self.fill(1, "request", ("Поиск работы", "Хочу найти первую работу."))
        nonce = self.bot.flow(1)["nonce"]
        update = self.update(1, f"f:{nonce}:send", True)
        self.bot.process(update)
        count = self.s.one("SELECT COUNT(*) FROM outbox")[0]
        self.bot.process(update)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM outbox")[0], count)
        self.action(1, f"f:{nonce}:send")
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 1)

    def test_full_employer_vacancy_application_invitation(self):
        self.participant()
        job = self.vacancy()
        self.action(1, f"job:{job}")
        self.assertIn("350 ₽", self.last(1)["text"])
        app = self.apply(job)
        self.assertIn("Новый отклик", self.last(2)["text"])
        self.action(2, f"application:{app}")
        self.assertIn("Саша", self.last(2)["text"])
        self.action(2, f"invite:{app}")
        self.assertEqual(self.s.one("SELECT status FROM applications")[0], "invited")
        self.assertIn("пригласил", self.last(1)["text"])

    def test_unapproved_employer_cannot_publish(self):
        self.fill(2, "employer", ("Магазин", "Анна, директор", "Казань"))
        self.choose(2, "send")
        self.action(2, "new:vacancy")
        self.assertIsNone(self.bot.flow(2))
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM vacancies")[0], 0)

    def test_admin_only_moderation(self):
        job = self.vacancy(approve=False)
        self.action(3, f"approve_vacancy:{job}")
        self.assertEqual(self.s.one("SELECT status FROM vacancies")[0], "pending")
        self.action(3, "admin")
        self.assertNotIn("Недоставленные сообщения", self.last(3)["text"])

    def test_old_approval_cannot_confirm_updated_employer(self):
        self.fill(2, "employer", ("Магазин", "Анна, директор", "Казань"))
        self.choose(2, "send")
        version = self.bot.member(2)["employer_consent_at"]
        self.action(100, f"reject_employer:2:{version}")
        self.message(100, "Уточните наименование организации.")
        self.choose(100, "send")
        self.fill(2, "employer", ("Новый магазин", "Анна, директор", "Казань"))
        self.choose(2, "send")
        self.action(100, f"approve_employer:2:{version}")
        self.assertEqual(self.bot.member(2)["employer_status"], "pending")
        self.assertIn("обновилась", self.last(100)["text"])

    def test_multiple_coordinators_cannot_reverse_completed_review(self):
        job = self.vacancy(approve=False)
        self.action(100, f"reject_vacancy:{job}")
        self.message(100, "Уточните график.")
        self.action(100, f"approve_vacancy:{job}")
        self.choose(100, "send")
        self.assertEqual(self.s.one("SELECT status FROM vacancies")[0], "approved")

    def test_vacancy_applicants_pagination(self):
        job = self.vacancy()
        for uid in range(10, 17):
            self.message(uid, "/start")
            self.participant(uid)
            self.apply(job, uid)
        self.action(2, f"applicants:{job}:0")
        payload = self.last(2)
        buttons = [item for row in payload["reply_markup"]["inline_keyboard"] for item in row]
        self.assertEqual(len([item for item in buttons if item["callback_data"].startswith("application:")]), 5)
        self.assertTrue(any(item["text"] == "Следующие →" for item in buttons))
        self.action(2, f"applicants:{job}:1")
        buttons = [item for row in self.last(2)["reply_markup"]["inline_keyboard"] for item in row]
        self.assertEqual(len([item for item in buttons if item["callback_data"].startswith("application:")]), 2)

    def test_pending_jobs_not_public(self):
        self.participant()
        job = self.vacancy(approve=False)
        self.action(1, f"job:{job}")
        self.assertEqual(self.last(1)["text"], "Вакансия недоступна.")
        self.action(1, f"apply:{job}")
        self.assertIsNone(self.bot.flow(1))

    def test_age_filter_applies_to_forged_callbacks(self):
        self.participant(age="14–15 лет")
        job = self.vacancy(age="18 лет и старше")
        self.action(1, f"apply:{job}")
        self.assertIsNone(self.bot.flow(1))
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 0)

    def test_under14_can_request_help(self):
        self.participant(age="До 14 лет")
        self.action(1, "jobs:0")
        self.assertIn("Подходящих вакансий пока нет", self.last(1)["text"])
        self.fill(1, "request", ("Другой вопрос", "Хочу узнать, как проходят занятия."))
        self.choose(1, "send")
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 1)

    def test_other_employer_cannot_read_applicant(self):
        self.participant()
        job = self.vacancy()
        app = self.apply(job)
        self.action(3, f"application:{app}")
        self.assertEqual(self.last(3)["text"], "Заявка недоступна.")
        self.action(3, f"applicants:{job}:0")
        self.assertEqual(self.last(3)["text"], "Отклики недоступны.")
        self.action(3, f"invite:{app}")
        self.assertEqual(self.s.one("SELECT status FROM applications")[0], "new")

    def test_withdraw_notifies_employer_and_prevents_invitation(self):
        self.participant()
        job = self.vacancy()
        app = self.apply(job)
        self.action(1, f"withdraw:{app}")
        self.choose(1, "send")
        self.assertEqual(self.s.one("SELECT status FROM applications")[0], "withdrawn")
        self.assertIn("отозван", self.last(2)["text"])
        self.action(2, f"invite:{app}")
        self.assertEqual(self.s.one("SELECT status FROM applications")[0], "withdrawn")

    def test_closing_vacancy_during_draft_prevents_application(self):
        self.participant()
        job = self.vacancy()
        self.action(1, f"apply:{job}")
        self.message(1, "Хочу попробовать эту работу.")
        self.action(2, f"closejob:{job}")
        self.choose(2, "send")
        self.choose(1, "send")
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 0)

    def test_cannot_apply_twice(self):
        self.participant()
        job = self.vacancy()
        self.apply(job)
        self.action(1, f"apply:{job}")
        self.assertIsNone(self.bot.flow(1))
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 1)

    def test_snapshots_survive_profile_change(self):
        self.participant()
        self.apply(self.vacancy())
        self.participant(name="Александр")
        snapshot = json.loads(self.s.one("SELECT snapshot FROM applications")[0])
        self.assertEqual(snapshot["name"], "Саша")

    def test_validation_and_html_escaping(self):
        self.action(1, "register:participant")
        self.choose(1, "consent")
        self.message(1, "А" * 61)
        self.assertEqual(self.bot.flow(1)["step"], 0)
        self.message(1, "<b>Саша</b>")
        self.choose(1, "3")
        self.message(1, "Ульяновск")
        self.choose(1, "0")
        self.assertIn("&lt;b&gt;Саша&lt;/b&gt;", self.last(1)["text"])

    def test_group_messages_ignored(self):
        update = self.update(1, "/start")
        update["message"]["chat"]["type"] = "group"
        count = self.s.one("SELECT COUNT(*) FROM outbox")[0]
        self.bot.process(update)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM outbox")[0], count)

    def test_rollback_preserves_offset_and_domain_state(self):
        update = self.update(1, "/menu")
        offset = self.s.offset()
        count = self.s.one("SELECT COUNT(*) FROM outbox")[0]
        with patch.object(self.bot, "handle", side_effect=RuntimeError("temporary failure")):
            with self.assertRaises(RuntimeError):
                self.bot.process(update)
        self.assertEqual(self.s.offset(), offset)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM outbox")[0], count)
        self.bot.process(update)
        self.assertEqual(self.s.offset(), update["update_id"] + 1)

    def test_rejection_requires_reason_and_notifies_employer(self):
        job = self.vacancy(approve=False)
        self.action(100, f"reject_vacancy:{job}")
        self.message(100, "Уточните порядок оформления и продолжительность смены.")
        self.choose(100, "send")
        self.assertEqual(self.s.one("SELECT status FROM vacancies")[0], "rejected")
        self.assertIn("порядок оформления", self.last(2)["text"])

    def test_notifications_retry_without_duplicate_domain_changes(self):
        self.s.execute("DELETE FROM outbox")
        self.participant()
        self.fill(1, "request", ("Другой вопрос", "Помогите разобраться с расходами."))
        self.choose(1, "send")
        api = Telegram("unused")
        with patch.object(api, "call", side_effect=TelegramError(429, retry_after=12)):
            api.flush(self.s)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM applications")[0], 1)
        self.assertEqual(self.s.one("SELECT attempts FROM outbox ORDER BY id LIMIT 1")[0], 1)
        self.s.execute("UPDATE outbox SET available_at=0")
        with patch.object(api, "call", return_value={}) as send:
            api.flush(self.s)
        self.assertGreater(send.call_count, 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM outbox")[0], 0)

    def test_blocked_user_does_not_block_other_replies(self):
        self.s.execute("DELETE FROM outbox")
        self.s.enqueue("sendMessage", {"chat_id": 1, "text": "A"})
        self.s.enqueue("sendMessage", {"chat_id": 2, "text": "B"})
        api = Telegram("unused")
        with patch.object(api, "call", side_effect=[TelegramError(403), {}]):
            api.flush(self.s)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM outbox WHERE status='failed'")[0], 1)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM outbox WHERE status='pending'")[0], 0)

    def test_callback_size_and_message_limits(self):
        self.participant()
        self.apply(self.vacancy())
        for row in self.s.all("SELECT payload FROM outbox"):
            payload = json.loads(row[0])
            if "text" in payload:
                self.assertLess(len(payload["text"]), 4096)
            for buttons in payload.get("reply_markup", {}).get("inline_keyboard", []):
                for item in buttons:
                    self.assertLessEqual(len(item["callback_data"].encode()), 64)


if __name__ == "__main__":
    unittest.main()
