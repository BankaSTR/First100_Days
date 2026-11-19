"""Conversation and access rules. No network I/O runs inside a database transaction."""
from dataclasses import dataclass
from html import escape
import json
import secrets
import time

TEXT_DASHES = str.maketrans({0x2013: "-", 0x2014: "-"})

AGES = ("До 14 лет", "14–15 лет", "16–17 лет", "18 лет и старше")
TOPICS = ("Участие в программе", "Поиск работы", "Резюме и собеседование", "Бюджет и бытовые вопросы", "Другой вопрос")
STATES = {"new": "Получена", "in_progress": "В работе", "done": "Завершена", "withdrawn": "Отозвана", "invited": "Приглашение", "rejected": "Отказ"}
EMPLOYERS = {"none": "Не заполнена", "pending": "На проверке", "approved": "Подтверждена", "rejected": "Нужны уточнения", "catalog": "Из открытых источников"}
JOBS = {"pending": "На проверке", "approved": "Опубликована", "rejected": "Отклонена", "closed": "Закрыта", "catalog": "Из открытых источников"}


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    prompt: str
    limit: int = 120
    options: tuple = ()


FORMS = {
    "participant": (
        Field("name", "Имя", "Как к тебе обращаться? Можно указать только имя.", 60),
        Field("age", "Возрастная группа", "Выбери возрастную группу.", options=AGES),
        Field("city", "Город", "В каком городе ты живёшь?", 80),
        Field("goal", "Цель", "С чем хочешь разобраться в первую очередь?", options=("Найти работу", "Подготовиться к выпуску", "Разобраться с бытом", "Пока хочу узнать о программе")),
    ),
    "employer": (
        Field("company", "Организация", "Как называется ваша организация?", 120),
        Field("contact", "Представитель", "Как к вам обращаться? Укажите имя и должность.", 100),
        Field("employer_city", "Город", "В каком городе работает организация?", 80),
    ),
    "request": (
        Field("topic", "Тема", "С чем нужна помощь?", options=TOPICS),
        Field("body", "Обращение", "Коротко расскажи, что хочешь сделать и с чем нужна помощь. До 700 символов. Документы и личные номера присылать не нужно.", 700),
    ),
    "vacancy": (
        Field("title", "Должность", "На какую должность ищете сотрудника?", 80),
        Field("city", "Город", "Где предстоит работать? Укажите город или напишите «Удалённо».", 80),
        Field("schedule", "График", "Какой график вы предлагаете? Укажите дни и часы, возможность совмещать с учёбой.", 160),
        Field("pay", "Оплата", "Укажите сумму, период и условия оплаты. Например, 350 ₽ в час, до вычета налога.", 160),
        Field("age", "Возраст", "С какой возрастной группы готовы рассматривать кандидатов? Координатор проверит условия перед публикацией.", options=("14–15 лет", "16–17 лет", "18 лет и старше")),
        Field("description", "Задачи и условия", "Опишите задачи, обучение, оформление и требования. До 700 символов.", 700),
    ),
    "apply": (Field("body", "Отклик", "Напиши 2–5 предложений о себе. Что умеешь, почему интересна работа, когда удобно начать? До 700 символов.", 700),),
    "reply": (Field("body", "Ответ", "Напишите ответ участнику. Он получит его в этом боте. До 700 символов.", 700),),
    "reject_employer": (Field("body", "Что уточнить", "Что нужно уточнить в организации? Представитель получит ваше сообщение.", 700),),
    "reject_vacancy": (Field("body", "Причина", "Почему вакансия отклонена? Работодатель получит ваше сообщение.", 700),),
}


BUTTON_ICONS = {
    "Меню": "🏠",
    "Открыть меню": "🏠",
    "Продолжить": "▶️",
    "Продолжить заполнение": "▶️",
    "Согласен · Продолжить": "✅",
    "Я участник": "👤",
    "Я участник · Регистрация": "👤",
    "Регистрация участника": "📝",
    "Изменить анкету": "✏️",
    "Моя анкета": "👤",
    "Я работодатель": "🏢",
    "Работодатель": "🏢",
    "Регистрация организации": "🏢",
    "Моя организация": "🏢",
    "Сменить роль": "🔄",
    "О программе": "ℹ️",
    "О данных": "🔒",
    "Подать заявку": "📝",
    "Нужна помощь": "🙋",
    "Написать координатору": "💬",
    "Мои заявки": "📨",
    "Мои обращения": "📨",
    "Открыть заявку": "📨",
    "Отозвать заявку": "↩️",
    "Вакансии": "💼",
    "Предложить вакансию": "➕",
    "Предложить новую вакансию": "➕",
    "Мои вакансии": "💼",
    "Мои вакансии и отклики": "💼",
    "К вакансии": "💼",
    "Закрыть вакансию": "🔒",
    "Откликнуться": "✉️",
    "Отправить": "📤",
    "Подтвердить": "✅",
    "Назад": "⬅️",
    "Назад · Исправить": "⬅️",
    "Предыдущие": "⬅️",
    "Следующие": "➡️",
    "Отмена": "🚫",
    "Оставить как есть": "↩️",
    "Удалить черновик": "🗑️",
    "Показать варианты": "☑️",
    "Зарегистрироваться": "📝",
    "Регистрация": "📝",
    "Кабинет координатора": "🛠️",
    "Организации": "🏢",
    "Участники": "👥",
    "Помочь с откликом": "✉️",
    "Заявки и отклики": "📨",
    "Повторить доставку сообщений": "🔄",
    "Ответить": "💬",
    "Взять в работу": "📋",
    "Завершить": "✅",
    "Пригласить": "🤝",
    "Отказать": "❌",
    "Проверить": "🔍",
    "Открыть анкету": "👤",
    "Запросить уточнение": "💬",
    "Опубликовать": "📣",
    "Отклонить": "❌",
    "Открыть": "📂",
    "Участие в программе": "🎓",
    "Поиск работы": "💼",
    "Резюме и собеседование": "📝",
    "Бюджет и бытовые вопросы": "🏠",
    "Другой вопрос": "💬",
    "Найти работу": "💼",
    "Подготовиться к выпуску": "🎓",
    "Разобраться с бытом": "🏠",
    "Пока хочу узнать о программе": "ℹ️",
    **dict.fromkeys(AGES, "👤"),
}


def button(label, data):
    label = label.removeprefix("← ").removesuffix(" →").translate(TEXT_DASHES)
    action = data.split(":", 1)[0]
    icon = BUTTON_ICONS.get(label)
    if icon is None:
        icon = {"job": "💼", "application": "📨", "employer": "🏢", "participant": "👤", "applicants": "📨"}.get(action, "📂")
    return {"text": f"{icon} {label}", "callback_data": data}


def text(value):
    return escape(str(value))


class Bot:
    def __init__(self, store, config):
        self.s = store
        self.config = config

    def send(self, user_id, body, rows=None):
        # Imported companies and fictional participants are never Telegram recipients.
        if user_id <= 0:
            return
        payload = {"chat_id": user_id, "text": body.translate(TEXT_DASHES), "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
        if rows:
            payload["reply_markup"] = {"inline_keyboard": rows}
        self.s.enqueue("sendMessage", payload)

    def admins(self, body, rows=None):
        for admin in sorted(self.config.admin_ids):
            self.send(admin, body, rows)

    def member(self, user_id):
        return self.s.one("SELECT * FROM members WHERE id=?", (user_id,))

    def flow(self, user_id):
        row = self.s.one("SELECT * FROM flows WHERE user_id=?", (user_id,))
        return dict(row) | {"data": json.loads(row["data"])} if row else None

    def save_flow(self, user_id, kind, step=0, data=None):
        self.s.execute("INSERT INTO flows VALUES (?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET kind=excluded.kind,step=excluded.step,data=excluded.data,nonce=excluded.nonce,updated_at=excluded.updated_at",
                       (user_id, kind, step, json.dumps(data or {}, ensure_ascii=False), secrets.token_hex(4), int(time.time())))

    def clear_flow(self, user_id):
        self.s.execute("DELETE FROM flows WHERE user_id=?", (user_id,))

    def process(self, update):
        with self.s.transaction():
            if self.s.processed(update["update_id"]):
                return
            self.handle(update)
            self.s.finish(update["update_id"])

    def handle(self, update):
        callback = update.get("callback_query")
        message = callback.get("message") if callback else update.get("message")
        sender = callback.get("from") if callback else (message or {}).get("from")
        if not sender or not message or message.get("chat", {}).get("type") != "private" or sender.get("is_bot"):
            return
        user_id = sender["id"]
        if user_id <= 0 or message["chat"]["id"] != user_id:
            return
        self.s.execute("INSERT OR IGNORE INTO members(id,created_at) VALUES (?,?)", (user_id, int(time.time())))
        if callback:
            self.s.enqueue("answerCallbackQuery", {"callback_query_id": callback["id"]})
            self.action(user_id, callback.get("data", ""))
            return
        value = message.get("text", "").strip()
        command = value.split(maxsplit=1)[0].split("@")[0].lower() if value else ""
        if command == "/id":
            self.send(user_id, f"Твой Telegram ID - <code>{user_id}</code>.")
        elif command in ("/start", "/menu"):
            self.menu(user_id)
        elif command == "/admin":
            self.admin_menu(user_id)
        elif command == "/privacy":
            self.privacy(user_id)
        elif command == "/help":
            self.send(user_id, "<b>Как пользоваться ботом</b>\n\nВыбери роль и заполни короткую анкету. После регистрации можно отправить заявку или отклик.\n\n/menu - открыть меню\n/cancel - отменить заполнение\n/privacy - какие данные сохраняются\n\nЕсли ошибся в анкете, нажми «Назад». Перед отправкой покажу всё целиком.", [[button("Открыть меню", "menu")]])
        elif command == "/cancel":
            if self.flow(user_id):
                self.cancel_prompt(user_id)
            else:
                self.menu(user_id)
        elif command.startswith("/"):
            self.send(user_id, "Такой команды нет. Открой меню или продолжи заполнение.", [[button("Меню", "menu")]])
        elif self.flow(user_id):
            self.input(user_id, value)
        else:
            self.send(user_id, "Выбери действие в меню. Чтобы отправить сообщение координатору, нажми «Нужна помощь».", [[button("Открыть меню", "menu")]])

    def menu(self, user_id):
        user = self.member(user_id)
        rows = []
        if self.flow(user_id):
            rows.append([button("Продолжить заполнение", "resume")])
        if user["role"] == "employer":
            body = "<b>Первые 100 дней · Работодателю</b>\n\nПредложите первую работу или практику. Координатор проверит организацию и условия вакансии."
            if user["employer_status"] == "approved":
                rows += [[button("Предложить вакансию", "new:vacancy")], [button("Мои вакансии и отклики", "ownjobs:0")]]
            else:
                rows.append([button("Регистрация организации", "register:employer")])
            rows += [[button("Моя организация", "profile"), button("Мои обращения", "applications:0")], [button("Написать координатору", "new:request")]]
        else:
            body = "<b>Первые 100 дней</b>\n\nПоможем подготовиться к самостоятельной жизни и сделать первые шаги после выпуска. Здесь можно зарегистрироваться, попросить помощь и найти первую работу."
            if user["consent_at"]:
                rows += [[button("Нужна помощь", "new:request"), button("Вакансии", "jobs:0")], [button("Мои заявки", "applications:0"), button("Моя анкета", "profile")]]
            else:
                rows.append([button("Я участник · Регистрация", "register:participant")])
                rows.append([button("Я работодатель", "role:employer")])
        rows += [[button("Сменить роль", "roles"), button("О программе", "about")]]
        if user_id in self.config.admin_ids:
            rows.append([button("Кабинет координатора", "admin")])
        self.send(user_id, body, rows)

    def privacy(self, user_id):
        rows = [[button("Меню", "menu")]]
        if self.flow(user_id):
            rows.insert(0, [button("Продолжить", "resume")])
        self.send(
            user_id,
            f"<b>О твоих данных</b>\n\n{text(self.config.operator)} сохраняет анкету, "
            "черновики и заявки, чтобы отвечать тебе в Telegram. Их видят координаторы.\n\n"
            "Работодателю передаём имя, возрастную группу, город и отклик после твоего подтверждения.\n\n"
            "Чтобы изменить или удалить данные, напиши координатору.",
            rows,
        )

    def action(self, user_id, data):
        parts = data.split(":")
        action = parts[0]
        if action == "f":
            self.flow_action(user_id, parts)
        elif data == "menu":
            self.menu(user_id)
        elif data == "resume":
            if self.flow(user_id):
                self.prompt(user_id)
            else:
                self.menu(user_id)
        elif data == "roles":
            self.send(user_id, "<b>Как хочешь пользоваться ботом?</b>\nАнкета участника и организация сохранятся при смене роли.", [[button("Я участник", "role:participant"), button("Я работодатель", "role:employer")]])
        elif action == "role" and len(parts) == 2 and parts[1] in ("participant", "employer"):
            self.s.execute("UPDATE members SET role=? WHERE id=?", (parts[1], user_id))
            self.menu(user_id)
        elif data == "about":
            user = self.member(user_id)
            if user["consent_at"] or user["employer_consent_at"]:
                next_button = button("Подать заявку", "new:request")
            else:
                next_button = button("Подать заявку", "register:" + user["role"])
            self.send(
                user_id,
                "<b>Первые 100 дней</b>\n\n"
                "Помогаем с первой работой и бытовыми вопросами.\n\n"
                "Оставь заявку - координатор ответит здесь, в Telegram. Участие бесплатное.",
                [[next_button], [button("Меню", "menu")]],
            )
        elif data == "privacy":
            self.privacy(user_id)
        elif action == "register" and len(parts) == 2 and parts[1] in ("participant", "employer"):
            kind = parts[1]
            user = self.member(user_id)
            if kind == "employer" and user["employer_status"] in ("pending", "approved"):
                self.profile(user_id)
            else:
                self.begin(user_id, kind, -1)
        elif data == "profile":
            self.profile(user_id)
        elif action == "new" and len(parts) == 2 and parts[1] in ("request", "vacancy"):
            user = self.member(user_id)
            if parts[1] == "vacancy" and user["employer_status"] != "approved":
                self.send(user_id, "Публиковать вакансии можно после проверки организации.", [[button("Меню", "menu")]])
            elif parts[1] == "request" and not (user["consent_at"] or user["employer_consent_at"]):
                self.send(user_id, "Сначала заполни анкету - так координатор поймёт, кому отвечает.", [[button("Регистрация участника", "register:participant"), button("Работодатель", "register:employer")]])
            else:
                self.begin(user_id, parts[1])
        elif action in ("jobs", "ownjobs", "applications") and len(parts) == 2 and parts[1].isdigit():
            self.list_items(user_id, action, int(parts[1]))
        elif action in ("job", "application") and len(parts) == 2 and parts[1].isdigit():
            if action == "job":
                self.job(user_id, int(parts[1]))
            else:
                self.application(user_id, int(parts[1]))
        elif action == "apply" and len(parts) == 2 and parts[1].isdigit():
            self.begin_apply(user_id, int(parts[1]))
        elif action == "withdraw" and len(parts) == 2 and parts[1].isdigit():
            self.withdraw(user_id, int(parts[1]))
        elif action == "closejob" and len(parts) == 2 and parts[1].isdigit():
            self.begin_close(user_id, int(parts[1]))
        elif action == "applicants" and len(parts) == 3 and all(part.isdigit() for part in parts[1:]):
            self.applicants(user_id, int(parts[1]), int(parts[2]))
        elif action == "admin":
            self.admin_menu(user_id)
        elif action == "retry_notifications":
            if user_id in self.config.admin_ids:
                self.s.execute("UPDATE outbox SET status='pending',attempts=0,available_at=0 WHERE status='failed'")
                self.send(user_id, "Повторная доставка поставлена в очередь.", [[button("Кабинет координатора", "admin")]])
            else:
                self.send(user_id, "Это действие доступно координатору.")
        elif action == "queue" and len(parts) == 3 and parts[2].isdigit():
            self.queue(user_id, parts[1], int(parts[2]))
        elif action == "participant" and len(parts) == 2 and parts[1].lstrip("-").isdigit():
            self.participant_card(user_id, int(parts[1]))
        elif action in ("approve_employer", "reject_employer") and len(parts) == 3 and all(part.isdigit() for part in parts[1:]):
            self.management(user_id, action, int(parts[1]), int(parts[2]))
        elif action in ("employer", "approve_vacancy", "reject_vacancy", "reply", "take", "done", "invite", "reject") and len(parts) == 2 and (parts[1].isdigit() or (action == "employer" and parts[1].lstrip("-").isdigit())):
            self.management(user_id, action, int(parts[1]))
        else:
            self.send(user_id, "Кнопка устарела. Открой меню.", [[button("Меню", "menu")]])

    def begin(self, user_id, kind, step=0, data=None):
        if self.flow(user_id):
            self.send(user_id, "Есть незаконченная форма. Можно продолжить её или отменить командой /cancel.", [[button("Продолжить", "resume"), button("Меню", "menu")]])
            return
        self.save_flow(user_id, kind, step, data)
        self.prompt(user_id)

    def prompt(self, user_id):
        flow = self.flow(user_id)
        kind, step, data, nonce = flow["kind"], flow["step"], flow["data"], flow["nonce"]
        prefix = f"f:{nonce}:"
        if kind in ("withdraw", "closejob"):
            self.send(user_id, "Отозвать заявку? Координатор и работодатель увидят новый статус." if kind == "withdraw" else "Закрыть вакансию? Новые отклики приниматься не будут.", [[button("Подтвердить", prefix + "send"), button("Оставить как есть", prefix + "cancel")]])
            return
        if step == -1:
            self.send(
                user_id,
                "<b>Регистрация</b>\n\nЗаполни короткую анкету. "
                "Сохраним ответы, чтобы связаться с тобой по заявке.",
                [[button("Согласен · Продолжить", prefix + "consent")],
                 [button("О данных", "privacy"), button("Отмена", prefix + "cancel")]],
            )
            return
        fields = FORMS[kind]
        if step == len(fields):
            summary = "\n".join(f"<b>{field.label}</b> - {text(data[field.key])}" for field in fields)
            note = ""
            if kind == "apply":
                user = self.member(user_id)
                note = f"\n\nРаботодателю будут переданы имя {text(user['name'])}, возрастная группа {text(user['age'])}, город {text(user['city'])} и этот отклик."
                job = self.s.one("SELECT status FROM vacancies WHERE id=?", (data["vacancy_id"],))
                if job and job["status"] == "catalog":
                    note = "\n\nАнкету и отклик получит координатор. Он поможет связаться с работодателем."
            self.send(user_id, "<b>Проверь перед отправкой</b>\n\n" + summary + note, [[button("Отправить", prefix + "send")], [button("Назад · Исправить", prefix + "back"), button("Отмена", prefix + "cancel_prompt")]])
            return
        field = fields[step]
        rows = [[button(option, prefix + str(index))] for index, option in enumerate(field.options)]
        if step > 0:
            rows.append([button("Назад", prefix + "back"), button("Отмена", prefix + "cancel_prompt")])
        else:
            rows.append([button("Отмена", prefix + "cancel_prompt")])
        self.send(user_id, f"<b>Шаг {step + 1} из {len(fields)}</b>\n\n{field.prompt}", rows)

    def cancel_prompt(self, user_id):
        flow = self.flow(user_id)
        prefix = f"f:{flow['nonce']}:"
        self.send(user_id, "Отменить заполнение? Черновик будет удалён, отправленные заявки сохранятся.", [[button("Удалить черновик", prefix + "cancel"), button("Продолжить", "resume")]])

    def flow_action(self, user_id, parts):
        flow = self.flow(user_id)
        if len(parts) != 3 or not flow or parts[1] != flow["nonce"]:
            self.send(user_id, "Этот шаг уже пройден. Продолжи актуальную форму.", [[button("Продолжить", "resume"), button("Меню", "menu")]])
            return
        choice = parts[2]
        if choice == "cancel":
            self.clear_flow(user_id)
            self.menu(user_id)
        elif choice == "cancel_prompt":
            self.cancel_prompt(user_id)
        elif choice == "consent" and flow["step"] == -1:
            self.save_flow(user_id, flow["kind"], 0, flow["data"] | {"_consent": time.time_ns()})
            self.prompt(user_id)
        elif choice == "back" and flow["step"] > 0 and flow["kind"] in FORMS:
            self.save_flow(user_id, flow["kind"], flow["step"] - 1, flow["data"])
            self.prompt(user_id)
        elif choice == "send" and (flow["kind"] in ("withdraw", "closejob") or flow["step"] == len(FORMS[flow["kind"]])):
            self.submit(user_id, flow)
        elif flow["kind"] in FORMS and 0 <= flow["step"] < len(FORMS[flow["kind"]]):
            options = FORMS[flow["kind"]][flow["step"]].options
            if choice.isdigit() and int(choice) < len(options):
                self.input(user_id, options[int(choice)], from_button=True)

    def input(self, user_id, value, from_button=False):
        flow = self.flow(user_id)
        if flow["kind"] not in FORMS or not 0 <= flow["step"] < len(FORMS[flow["kind"]]):
            self.send(user_id, "Подтверди действие кнопкой под сообщением.", [[button("Продолжить", "resume")]])
            return
        field = FORMS[flow["kind"]][flow["step"]]
        if field.options and (not from_button or value not in field.options):
            self.send(user_id, "Выбери вариант кнопкой под текущим вопросом.", [[button("Показать варианты", "resume")]])
            return
        if not 2 <= len(value) <= field.limit or any(ord(char) < 32 and char not in "\n\t" for char in value):
            self.send(user_id, f"Нужно от 2 до {field.limit} символов. Попробуй ещё раз. Если прислал фото или голосовое, напиши ответ текстом.")
            return
        self.save_flow(user_id, flow["kind"], flow["step"] + 1, flow["data"] | {field.key: value})
        self.prompt(user_id)

    def profile(self, user_id):
        user = self.member(user_id)
        employer = user["role"] == "employer"
        fields = FORMS["employer" if employer else "participant"]
        body = "\n".join(f"<b>{field.label}</b> - {text(user[field.key] or 'Не заполнено')}" for field in fields)
        rows = [[button("Меню", "menu")]]
        if employer:
            body += "\n<b>Проверка</b> - " + EMPLOYERS[user["employer_status"]]
        else:
            rows.insert(0, [button("Изменить анкету", "register:participant")])
        self.send(user_id, "<b>Моя организация</b>\n\n" + body if employer else "<b>Моя анкета</b>\n\n" + body, rows)

    def submit(self, user_id, flow):
        kind, data = flow["kind"], flow["data"]
        user = self.member(user_id)
        if kind == "participant":
            self.s.execute("UPDATE members SET name=?,age=?,city=?,goal=?,consent_at=?,role='participant' WHERE id=?", (data["name"], data["age"], data["city"], data["goal"], data["_consent"], user_id))
            self.send(user_id, "<b>Анкета сохранена</b>\n\nТеперь можно отправить заявку на участие, попросить помощь или выбрать вакансию.", [[button("Подать заявку", "new:request"), button("Вакансии", "jobs:0")], [button("Меню", "menu")]])
        elif kind == "employer":
            self.s.execute("UPDATE members SET company=?,contact=?,employer_city=?,employer_consent_at=?,employer_status='pending',role='employer' WHERE id=?", (data["company"], data["contact"], data["employer_city"], data["_consent"], user_id))
            self.send(user_id, "<b>Организация отправлена на проверку</b>\n\nКоординатор изучит анкету. Решение придёт сюда. После подтверждения сможете предложить вакансию.", [[button("Меню", "menu")]])
            self.admins("<b>Новая организация</b>\n" + text(data["company"]) + "\n" + text(data["employer_city"]), [[button("Проверить", f"employer:{user_id}")]])
        elif kind == "vacancy":
            if user["employer_status"] != "approved":
                self.send(user_id, "Сначала дождитесь подтверждения организации.")
                self.clear_flow(user_id)
                return
            cursor = self.s.execute("INSERT INTO vacancies(employer_id,company,title,city,schedule,pay,age,description,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (user_id, user["company"], data["title"], data["city"], data["schedule"], data["pay"], data["age"], data["description"], int(time.time())))
            self.send(user_id, f"<b>Вакансия №{cursor.lastrowid} на проверке</b>\n\nПосле проверки координатором она появится у участников.", [[button("Мои вакансии", "ownjobs:0")]])
            self.admins("<b>Новая вакансия</b>\n" + text(data["title"]), [[button("Проверить", f"job:{cursor.lastrowid}")]])
        elif kind in ("request", "apply"):
            self.submit_application(user_id, kind, data)
        elif kind in ("reply", "reject_employer", "reject_vacancy"):
            self.submit_admin(user_id, kind, data)
        elif kind == "withdraw":
            app = self.s.one("SELECT * FROM applications WHERE id=? AND user_id=?", (data["id"], user_id))
            if app and app["status"] in ("new", "in_progress", "invited"):
                self.s.execute("UPDATE applications SET status='withdrawn' WHERE id=?", (app["id"],))
                self.send(user_id, f"Заявка №{app['id']} отозвана.")
                self.admins(f"Участник отозвал заявку №{app['id']}.")
                if app["vacancy_id"]:
                    job = self.s.one("SELECT * FROM vacancies WHERE id=?", (app["vacancy_id"],))
                    self.send(job["employer_id"], f"Отклик №{app['id']} отозван участником.")
            else:
                self.send(user_id, "Заявка уже обработана или отозвана.")
        elif kind == "closejob":
            job = self.s.one("SELECT * FROM vacancies WHERE id=? AND employer_id=?", (data["id"], user_id))
            if job and job["status"] in ("approved", "pending"):
                self.s.execute("UPDATE vacancies SET status='closed' WHERE id=?", (job["id"],))
                self.send(user_id, f"Вакансия №{job['id']} закрыта. Существующие отклики доступны в её карточке.")
                self.admins(f"Работодатель закрыл вакансию №{job['id']}.")
            else:
                self.send(user_id, "Вакансия уже закрыта или недоступна.")
        self.clear_flow(user_id)

    def submit_application(self, user_id, kind, data):
        user = self.member(user_id)
        vacancy_id = data.get("vacancy_id")
        if kind == "apply":
            job = self.eligible_job(user_id, vacancy_id)
            if not job:
                self.send(user_id, "Вакансия сейчас недоступна для отклика. Выбери другую или обратись к координатору.")
                return
            if self.s.one("SELECT id FROM applications WHERE user_id=? AND vacancy_id=?", (user_id, vacancy_id)):
                self.send(user_id, "Отклик на эту вакансию уже есть в разделе «Мои заявки».")
                return
        snapshot = {key: user[key] for key in ("name", "age", "city", "company", "contact", "role")}
        cursor = self.s.execute("INSERT INTO applications(user_id,vacancy_id,topic,body,snapshot,created_at) VALUES (?,?,?,?,?,?)", (user_id, vacancy_id, data.get("topic", "Отклик на вакансию"), data["body"], json.dumps(snapshot, ensure_ascii=False), int(time.time())))
        app_id = cursor.lastrowid
        rows = [[button("Открыть заявку", f"application:{app_id}")]]
        recipient_note = "Координатор поможет связаться с работодателем. " if vacancy_id and job["status"] == "catalog" else ""
        self.send(user_id, f"<b>Заявка №{app_id} отправлена</b>\n\n{recipient_note}Статус - получена. Ответ придёт сюда. Следить за заявкой можно в меню.", rows)
        self.admins(f"<b>Новая заявка №{app_id}</b>\n" + text(data.get("topic", "Отклик на вакансию")), rows)
        if vacancy_id:
            self.send(job["employer_id"], f"<b>Новый отклик №{app_id}</b>\nНа вакансию «{text(job['title'])}».", rows)

    def eligible_job(self, user_id, vacancy_id):
        user = self.member(user_id)
        job = self.s.one("SELECT * FROM vacancies WHERE id=? AND status IN ('approved','catalog')", (vacancy_id,))
        if not job or not user["consent_at"] or user_id == job["employer_id"]:
            return None
        return job if AGES.index(user["age"]) >= AGES.index(job["age"]) else None

    def begin_apply(self, user_id, vacancy_id):
        user = self.member(user_id)
        if not user["consent_at"]:
            self.send(user_id, "Сначала заполни анкету участника.", [[button("Зарегистрироваться", "register:participant")]])
        elif self.eligible_job(user_id, vacancy_id):
            existing = self.s.one("SELECT id FROM applications WHERE user_id=? AND vacancy_id=?", (user_id, vacancy_id))
            if existing:
                self.application(user_id, existing["id"])
            else:
                self.begin(user_id, "apply", data={"vacancy_id": vacancy_id})
        else:
            self.send(user_id, "Сейчас нельзя откликнуться на эту вакансию. Посмотри другие предложения или напиши координатору.", [[button("Вакансии", "jobs:0"), button("Нужна помощь", "new:request")]])

    def list_items(self, user_id, kind, page):
        user = self.member(user_id)
        if kind == "jobs":
            if not user["consent_at"]:
                self.send(user_id, "Заполни анкету, чтобы увидеть подходящие по возрасту вакансии.", [[button("Регистрация", "register:participant")]])
                return
            ages = AGES[1:AGES.index(user["age"]) + 1]
            placeholders = ",".join("?" for _ in ages) or "NULL"
            items = self.s.all(f"SELECT id,title FROM vacancies WHERE status IN ('approved','catalog') AND age IN ({placeholders}) AND employer_id<>? ORDER BY id DESC LIMIT 6 OFFSET ?", (*ages, user_id, page * 5))
            title, prefix = "Вакансии", "job"
            empty = "Подходящих вакансий пока нет. Можно оставить заявку на помощь с поиском работы."
        elif kind == "ownjobs":
            items = self.s.all("SELECT id,title,status FROM vacancies WHERE employer_id=? ORDER BY id DESC LIMIT 6 OFFSET ?", (user_id, page * 5))
            title, prefix, empty = "Мои вакансии", "job", "Пока нет вакансий."
        else:
            items = self.s.all("SELECT id,topic AS title,status FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 6 OFFSET ?", (user_id, page * 5))
            title, prefix, empty = "Мои заявки", "application", "Ты ещё не отправлял заявки."
        rows = [[button(f"№{item['id']} · {item['title'][:36]}", f"{prefix}:{item['id']}")] for item in items[:5]]
        navigation = []
        if page:
            navigation.append(button("← Предыдущие", f"{kind}:{page - 1}"))
        if len(items) > 5:
            navigation.append(button("Следующие →", f"{kind}:{page + 1}"))
        if navigation:
            rows.append(navigation)
        rows.append([button("Меню", "menu")])
        self.send(user_id, f"<b>{title}</b>\n\n" + ("Выбери карточку." if items else empty), rows)

    def job(self, user_id, vacancy_id):
        job = self.s.one("SELECT * FROM vacancies WHERE id=?", (vacancy_id,))
        admin = user_id in self.config.admin_ids
        if not job or (job["status"] not in ("approved", "catalog") and job["employer_id"] != user_id and not admin):
            self.send(user_id, "Вакансия недоступна.")
            return
        age = "Уточняется у компании" if job["source_url"] else job["age"]
        body = (f"<b>{text(job['title'])}</b>\n{text(job['company'])}\n\n"
                f"Город - {text(job['city'])}\nГрафик - {text(job['schedule'])}\nОплата - {text(job['pay'])}\nВозраст - {text(age)}\n\n{text(job['description'])}\n\nСтатус - {JOBS[job['status']]}")
        rows = []
        if job["source_url"]:
            body += f"\n\nПодборка от {text(job['source_checked_on'])}. Наличие места и условия уточняются.\nКоординатор поможет связаться с работодателем."
            rows.append([{"text": "🔗 Источник", "url": job["source_url"]}])
        if admin and job["status"] == "pending":
            rows.append([button("Опубликовать", f"approve_vacancy:{vacancy_id}"), button("Отклонить", f"reject_vacancy:{vacancy_id}")])
        if job["employer_id"] == user_id or admin:
            count = self.s.one("SELECT COUNT(*) FROM applications WHERE vacancy_id=?", (vacancy_id,))[0]
            rows.append([button(f"Отклики · {count}", f"applicants:{vacancy_id}:0")])
            if job["employer_id"] == user_id and job["status"] in ("pending", "approved"):
                rows.append([button("Закрыть вакансию", f"closejob:{vacancy_id}")])
        elif self.eligible_job(user_id, vacancy_id):
            rows.append([button("Помочь с откликом" if job["status"] == "catalog" else "Откликнуться", f"apply:{vacancy_id}")])
        rows.append([button("Меню", "menu")])
        self.send(user_id, body, rows)

    def applicants(self, user_id, vacancy_id, page):
        job = self.s.one("SELECT * FROM vacancies WHERE id=?", (vacancy_id,))
        if not job or (job["employer_id"] != user_id and user_id not in self.config.admin_ids):
            self.send(user_id, "Отклики недоступны.")
            return
        items = self.s.all("SELECT id,status FROM applications WHERE vacancy_id=? ORDER BY id DESC LIMIT 6 OFFSET ?", (vacancy_id, page * 5))
        rows = [[button(f"№{item['id']} · {STATES[item['status']]}", f"application:{item['id']}")] for item in items[:5]]
        navigation = []
        if page:
            navigation.append(button("← Предыдущие", f"applicants:{vacancy_id}:{page - 1}"))
        if len(items) > 5:
            navigation.append(button("Следующие →", f"applicants:{vacancy_id}:{page + 1}"))
        if navigation:
            rows.append(navigation)
        rows.append([button("К вакансии", f"job:{vacancy_id}")])
        self.send(user_id, f"<b>Отклики · {text(job['title'])}</b>\n\n" + ("Выберите карточку." if items else "Пока нет откликов."), rows)

    def accessible_application(self, user_id, app_id):
        app = self.s.one("SELECT a.*,v.employer_id FROM applications a LEFT JOIN vacancies v ON v.id=a.vacancy_id WHERE a.id=?", (app_id,))
        if app and (user_id in self.config.admin_ids or user_id in (app["user_id"], app["employer_id"])):
            return app
        return None

    def application(self, user_id, app_id):
        app = self.accessible_application(user_id, app_id)
        if not app:
            self.send(user_id, "Заявка недоступна.")
            return
        snapshot = json.loads(app["snapshot"])
        identity = snapshot["name"] or snapshot["contact"]
        body = f"<b>Заявка №{app_id} · {STATES[app['status']]}</b>\n{text(app['topic'])}\n\n{text(identity)}"
        if snapshot["age"]:
            body += " · " + text(snapshot["age"]) + " · " + text(snapshot["city"])
        body += "\n\n" + text(app["body"])
        job = self.s.one("SELECT title,company,status FROM vacancies WHERE id=?", (app["vacancy_id"],)) if app["vacancy_id"] else None
        if job:
            body += f"\n\n<b>Вакансия</b>\n{text(job['title'])} · {text(job['company'])}"
            if job["status"] == "catalog":
                body += "\nОтклик передан координатору. Он поможет связаться с работодателем."
        if app["response"]:
            response = app["response"]
            if app["is_demo"] and response.startswith("Учебный пример: "):
                response = response.removeprefix("Учебный пример: ")
                response = response[:1].upper() + response[1:]
            body += "\n\n<b>Ответ координатора</b>\n" + text(response)
        rows = []
        if job:
            rows.append([button("К вакансии", f"job:{app['vacancy_id']}")])
        active = app["status"] in ("new", "in_progress", "invited")
        if user_id in self.config.admin_ids and active:
            rows.append([button("Ответить", f"reply:{app_id}")])
            if app["status"] == "new":
                rows.append([button("Взять в работу", f"take:{app_id}")])
            if not app["vacancy_id"] or app["employer_id"] < 0:
                rows.append([button("Завершить", f"done:{app_id}")])
        if user_id == app["employer_id"] and app["status"] in ("new", "in_progress"):
            rows.append([button("Пригласить", f"invite:{app_id}"), button("Отказать", f"reject:{app_id}")])
        if user_id == app["user_id"] and active:
            rows.append([button("Отозвать заявку", f"withdraw:{app_id}")])
        rows.append([button("Меню", "menu")])
        self.send(user_id, body, rows)

    def withdraw(self, user_id, app_id):
        app = self.s.one("SELECT * FROM applications WHERE id=? AND user_id=?", (app_id, user_id))
        if app and app["status"] in ("new", "in_progress", "invited"):
            self.begin(user_id, "withdraw", data={"id": app_id})
        else:
            self.send(user_id, "Эту заявку уже нельзя отозвать.")

    def begin_close(self, user_id, vacancy_id):
        job = self.s.one("SELECT * FROM vacancies WHERE id=? AND employer_id=?", (vacancy_id, user_id))
        if job and job["status"] in ("pending", "approved"):
            self.begin(user_id, "closejob", data={"id": vacancy_id})
        else:
            self.send(user_id, "Вакансия недоступна для закрытия.")

    def admin_menu(self, user_id):
        if user_id not in self.config.admin_ids:
            self.send(user_id, "Кабинет доступен координатору программы.")
            return
        counts = [self.s.one(sql)[0] for sql in (
            "SELECT COUNT(*) FROM members WHERE employer_status='pending'",
            "SELECT COUNT(*) FROM vacancies WHERE status='pending'",
            "SELECT COUNT(*) FROM applications WHERE is_demo=0 AND status IN ('new','in_progress','invited')",
            "SELECT COUNT(*) FROM outbox WHERE status='failed'",
        )]
        totals = [self.s.one(sql)[0] for sql in (
            "SELECT COUNT(*) FROM members WHERE consent_at IS NOT NULL AND origin='telegram'",
            "SELECT COUNT(*) FROM members WHERE origin='demo'",
            "SELECT COUNT(*) FROM members WHERE origin='catalog'",
            "SELECT COUNT(*) FROM applications WHERE is_demo=1",
            "SELECT COUNT(*) FROM vacancies WHERE status='catalog'",
        )]
        rows = [[button("Организации", "queue:employers:0"), button("Вакансии", "queue:vacancies:0")], [button("Участники", "queue:participants:0"), button("Заявки и отклики", "queue:applications:0")]]
        if counts[3]:
            rows.append([button("Повторить доставку сообщений", "retry_notifications")])
        rows.append([button("Меню", "menu")])
        demo_note = (f"\n\n<b>Демонстрационные данные: анкеты и заявки вымышлены.</b>\nАнкеты - {totals[1]}\nЗаявки - {totals[3]}" if totals[1] or totals[3] else "")
        self.send(user_id, f"<b>Кабинет координатора</b>\n\nОрганизации на проверке - {counts[0]}\nВакансии на проверке - {counts[1]}\nАктивные заявки - {counts[2]}\nУчастники - {totals[0]}\nНедоставленные сообщения - {counts[3]}\n\n<b>Каталог</b>\nОрганизации - {totals[2]}\nВакансии - {totals[4]}" + demo_note, rows)

    def participant_card(self, user_id, participant_id):
        if user_id not in self.config.admin_ids:
            self.send(user_id, "Это действие доступно координатору.")
            return
        person = self.member(participant_id)
        if not person or not (person["consent_at"] or person["origin"] == "demo"):
            self.send(user_id, "Анкета недоступна.")
            return
        body = "\n".join(f"<b>{field.label}</b> - {text(person[field.key])}" for field in FORMS["participant"])
        self.send(user_id, "<b>Анкета участника</b>\n\n" + body, [[button("Участники", "queue:participants:0"), button("Кабинет координатора", "admin")]])

    def queue(self, user_id, kind, page):
        if user_id not in self.config.admin_ids:
            self.send(user_id, "Это действие доступно координатору.")
            return
        queries = {
            "employers": ("SELECT id,company AS title,employer_status AS status FROM members WHERE employer_status<>'none' ORDER BY (employer_status='pending') DESC,company,id LIMIT 6 OFFSET ?", "employer"),
            "vacancies": ("SELECT id,title,status FROM vacancies ORDER BY (status='pending') DESC,id DESC LIMIT 6 OFFSET ?", "job"),
            "applications": ("SELECT id,topic AS title,status,is_demo FROM applications ORDER BY is_demo,id DESC LIMIT 6 OFFSET ?", "application"),
            "participants": ("SELECT id,name AS title,origin FROM members WHERE consent_at IS NOT NULL OR origin='demo' ORDER BY (origin='demo'),name,id LIMIT 6 OFFSET ?", "participant"),
        }
        if kind not in queries:
            return
        sql, prefix = queries[kind]
        items = self.s.all(sql, (page * 5,))
        rows = []
        for item in items[:5]:
            label = item["title"][:32]
            if kind == "applications":
                label = f"№{item['id']} · {STATES[item['status']]}"
            elif kind in ("employers", "vacancies"):
                label += " · " + (EMPLOYERS if kind == "employers" else JOBS)[item["status"]]
            rows.append([button(label, f"{prefix}:{item['id']}")])
        if page:
            rows.append([button("← Предыдущие", f"queue:{kind}:{page - 1}")])
        if len(items) > 5:
            rows.append([button("Следующие →", f"queue:{kind}:{page + 1}")])
        rows.append([button("Кабинет координатора", "admin")])
        title = {"employers": "Организации", "vacancies": "Вакансии", "participants": "Участники", "applications": "Заявки и отклики"}[kind]
        self.send(user_id, f"<b>{title} · страница {page + 1}</b>\n\n" + ("Выберите карточку." if items else "Здесь пока пусто."), rows)

    def management(self, user_id, action, item_id, revision=None):
        if action in ("invite", "reject"):
            app = self.accessible_application(user_id, item_id)
            if not app or app["employer_id"] != user_id or app["status"] not in ("new", "in_progress"):
                self.send(user_id, "Отклик уже обработан или недоступен.")
                return
            job = self.s.one("SELECT * FROM vacancies WHERE id=?", (app["vacancy_id"],))
            status = "invited" if action == "invite" else "rejected"
            self.s.execute("UPDATE applications SET status=? WHERE id=?", (status, item_id))
            message = ("Работодатель пригласил тебя обсудить вакансию. Координатор поможет согласовать встречу." if action == "invite" else "Работодатель завершил рассмотрение этого отклика. Координатор поможет выбрать следующий шаг.")
            self.send(app["user_id"], f"<b>Отклик №{item_id}</b>\n{text(job['title'])}\n\n{message}", [[button("Нужна помощь", "new:request"), button("Мои заявки", "applications:0")]])
            self.admins(f"Отклик №{item_id} - {STATES[status]}.", [[button("Открыть", f"application:{item_id}")]])
            self.application(user_id, item_id)
            return
        if user_id not in self.config.admin_ids:
            self.send(user_id, "Это действие доступно координатору.")
            return
        if action in ("employer", "approve_employer", "reject_employer"):
            employer = self.member(item_id)
            if not employer or employer["employer_status"] == "none" or (action != "employer" and employer["employer_status"] != "pending"):
                self.send(user_id, "Организация уже проверена или недоступна.")
                return
            if action != "employer" and revision != employer["employer_consent_at"]:
                self.send(user_id, "Анкета организации обновилась. Откройте её заново перед проверкой.", [[button("Открыть анкету", f"employer:{item_id}")]])
                return
            if action == "employer":
                version = employer["employer_consent_at"]
                rows = []
                if employer["employer_status"] == "pending":
                    rows.append([button("Подтвердить", f"approve_employer:{item_id}:{version}"), button("Запросить уточнение", f"reject_employer:{item_id}:{version}")])
                if employer["source_url"]:
                    rows.append([{"text": "🔗 Источник", "url": employer["source_url"]}])
                rows.append([button("Организации", "queue:employers:0")])
                self.send(user_id, f"<b>Организация</b>\n\n{text(employer['company'])}\n{text(employer['contact'])}\n{text(employer['employer_city'])}\n\n{EMPLOYERS[employer['employer_status']]}", rows)
            elif action == "approve_employer":
                self.s.execute("UPDATE members SET employer_status='approved' WHERE id=?", (item_id,))
                self.send(item_id, "<b>Организация подтверждена</b>\nТеперь вы можете предложить вакансию.", [[button("Предложить вакансию", "new:vacancy")]])
                self.send(user_id, "Организация подтверждена.")
            else:
                self.begin(user_id, action, data={"id": item_id, "revision": revision})
        elif action in ("approve_vacancy", "reject_vacancy"):
            job = self.s.one("SELECT * FROM vacancies WHERE id=? AND status='pending'", (item_id,))
            if not job:
                self.send(user_id, "Вакансия уже проверена или закрыта.")
            elif action == "reject_vacancy":
                self.begin(user_id, action, data={"id": item_id})
            else:
                employer = self.member(job["employer_id"])
                if employer["employer_status"] != "approved":
                    self.send(user_id, "Сначала подтвердите организацию.")
                    return
                self.s.execute("UPDATE vacancies SET status='approved' WHERE id=?", (item_id,))
                self.send(job["employer_id"], f"Вакансия «{text(job['title'])}» опубликована.", [[button("Открыть", f"job:{item_id}")]])
                self.send(user_id, "Вакансия опубликована.")
        else:
            app = self.accessible_application(user_id, item_id)
            if not app or app["status"] not in ("new", "in_progress", "invited"):
                self.send(user_id, "Заявка уже обработана или недоступна.")
            elif action == "reply":
                self.begin(user_id, "reply", data={"id": item_id})
            elif action == "take" and app["status"] == "new":
                self.s.execute("UPDATE applications SET status='in_progress' WHERE id=?", (item_id,))
                self.send(app["user_id"], f"Координатор взял заявку №{item_id} в работу.")
                self.application(user_id, item_id)
            elif action == "done" and (not app["vacancy_id"] or app["employer_id"] < 0):
                self.s.execute("UPDATE applications SET status='done' WHERE id=?", (item_id,))
                self.send(app["user_id"], f"Заявка №{item_id} завершена. Если появилась новая задача, можно отправить ещё одну заявку.")
                self.application(user_id, item_id)

    def submit_admin(self, user_id, kind, data):
        if user_id not in self.config.admin_ids:
            self.send(user_id, "Это действие доступно координатору.")
            return
        item_id = data["id"]
        if kind == "reply":
            app = self.accessible_application(user_id, item_id)
            if not app or app["status"] not in ("new", "in_progress", "invited"):
                self.send(user_id, "Заявка уже обработана или отозвана.")
                return
            self.s.execute("UPDATE applications SET response=?,status=CASE WHEN status='new' THEN 'in_progress' ELSE status END WHERE id=?", (data["body"], item_id))
            self.send(app["user_id"], f"<b>Ответ по заявке №{item_id}</b>\n\n{text(data['body'])}", [[button("Мои заявки", "applications:0")]])
        elif kind == "reject_employer":
            employer = self.member(item_id)
            if not employer or employer["employer_status"] != "pending" or employer["employer_consent_at"] != data["revision"]:
                self.send(user_id, "Организация уже проверена.")
                return
            self.s.execute("UPDATE members SET employer_status='rejected' WHERE id=?", (item_id,))
            self.send(item_id, "<b>Нужно уточнить анкету</b>\n\n" + text(data["body"]), [[button("Заполнить заново", "register:employer")]])
        else:
            job = self.s.one("SELECT * FROM vacancies WHERE id=? AND status='pending'", (item_id,))
            if not job:
                self.send(user_id, "Вакансия уже проверена или закрыта.")
                return
            self.s.execute("UPDATE vacancies SET status='rejected' WHERE id=?", (item_id,))
            self.send(job["employer_id"], f"<b>Вакансия №{item_id} отклонена</b>\n\n{text(data['body'])}", [[button("Предложить новую вакансию", "new:vacancy")]])
        saved_demo = kind == "reply" and app["is_demo"]
        self.send(user_id, "Ответ сохранён." if saved_demo else "Сообщение отправлено.", [[button("Кабинет координатора", "admin")]])
