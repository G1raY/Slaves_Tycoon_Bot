import telebot
from telebot import types
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
import random
import os
import json
import time
import threading
import requests

# -------------------- КОНФИГУРАЦИЯ --------------------
BOT_TOKEN = "your bot token"
CRYPTOBOT_API_TOKEN = "your cryptobot token"
ADMIN_IDS = [your admin id]  # Мой ID разработчика
CHANNEL_USERNAME = "your chanale username"
RUB_TO_USDT_RATE = your rate rub to usdt

# Настройки оплаты звёздами
STARS_TO_COINS_RATE = 1
SUGGESTED_STAR_AMOUNTS = [50, 100, 250, 500, 1000]

# Настройки пассивного дохода
MAX_INCOME_HOURS = 24

# Настройки кражи
STEAL_BASE_COST = 100
STEAL_COST_INCOME_MULTIPLIER = 10
STEAL_BASE_CHANCE = 0.4
STEAL_LEVEL_REDUCTION = 0.05
STEAL_VIP_BONUS = 0.2
STEAL_SHIELD_BLOCKS = True

# Настройки прокачки
MAX_SLAVE_LEVEL = 10
LEVEL_UP_BASE_COST = 50
LEVEL_UP_COST_MULTIPLIER = 2
LEVEL_UP_BASE_TIME = 3600
LEVEL_UP_TIME_MULTIPLIER = 2

# Настройки щита
SHIELD_PRICES = {
    24: 50,
    72: 150,
    168: 300
}

VIP_PRICE_STARS = 150
VIP_DURATION_DAYS = 30

bot = telebot.TeleBot(BOT_TOKEN)

# -------------------- ФАЙЛЫ ДАННЫХ --------------------
USERS_DB = "users.json"
SUPPORT_REQUESTS_DB = "support_requests.json"
MARKET_DB = "market.json"

# -------------------- ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ СОСТОЯНИЙ --------------------
user_states = {}

# -------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------------------
def format_time(timestamp):
    if timestamp == 0 or timestamp == float('inf'):
        return "навсегда (разработчик)"
    dt = time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))
    return dt

def is_developer(user_id):
    """Проверяет, является ли пользователь разработчиком."""
    return user_id in ADMIN_IDS

def is_vip(user_data):
    """Проверяет, активен ли VIP у пользователя (разработчик считается VIP)."""
    user_id = user_data.get("id")
    if is_developer(user_id):
        return True
    return user_data.get("vip_expires", 0) > time.time()

def get_display_name(user_data):
    """Возвращает имя со статусным смайликом."""
    user_id = user_data.get("id")
    name = user_data.get("first_name", "Unknown")
    if is_developer(user_id):
        return f"🔧 {name}"
    if is_vip(user_data):
        return f"⭐ {name}"
    return name

def has_permanent_shield(user_id):
    """Бесконечный щит для разработчика."""
    return is_developer(user_id)

def get_shield_expires(user_data):
    """Возвращает время окончания щита (учитывая бесконечный для разработчика)."""
    user_id = user_data.get("id")
    if has_permanent_shield(user_id):
        return float('inf')
    return user_data.get("shield_expires", 0)

def remove_self_enslavement(user_id):
    """Удаляет пользователя из его собственного списка рабов."""
    user = get_user(user_id)
    if user and user_id in user.get("slaves", []):
        user["slaves"].remove(user_id)
        user["sum_slaves"] = len(user["slaves"])
        update_user(user_id, user)
        return True
    return False

def get_owner(user_id):
    """Возвращает данные владельца, если пользователь в рабстве, иначе None."""
    users = load_users()
    for uid, data in users.items():
        if user_id in data.get("slaves", []):
            return data
    return None

# -------------------- ФУНКЦИИ ДЛЯ РЫНКА --------------------
def load_market():
    if os.path.exists(MARKET_DB):
        with open(MARKET_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_market(market):
    with open(MARKET_DB, "w", encoding="utf-8") as f:
        json.dump(market, f, indent=4, ensure_ascii=False)

def add_market_offer(seller_id, slave_id, price):
    market = load_market()
    offer_id = str(int(time.time())) + str(seller_id)
    market[offer_id] = {
        "seller_id": seller_id,
        "slave_id": slave_id,
        "price": price,
        "created_at": time.time()
    }
    save_market(market)
    return offer_id

def remove_market_offer(offer_id):
    market = load_market()
    if offer_id in market:
        del market[offer_id]
        save_market(market)
        return True
    return False

def get_market_offers():
    market = load_market()
    offers = []
    for oid, data in market.items():
        slave_data = get_user(data["slave_id"])
        if slave_data and not slave_data.get("blocked"):
            offers.append({
                "offer_id": oid,
                "seller_id": data["seller_id"],
                "slave_id": data["slave_id"],
                "slave_name": get_display_name(slave_data),
                "price": data["price"],
                "slave_price": calculate_price(slave_data),
                "income": get_slave_income(slave_data)
            })
    return offers

def get_user_offers(user_id):
    market = load_market()
    user_offers = []
    for oid, data in market.items():
        if data["seller_id"] == user_id:
            slave_data = get_user(data["slave_id"])
            if slave_data:
                user_offers.append({
                    "offer_id": oid,
                    "slave_id": data["slave_id"],
                    "slave_name": get_display_name(slave_data),
                    "price": data["price"]
                })
    return user_offers

# -------------------- ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ --------------------
def load_users():
    if os.path.exists(USERS_DB):
        with open(USERS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_DB, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

def get_user(user_id):
    users = load_users()
    return users.get(str(user_id))

def update_user(user_id, data):
    users = load_users()
    users[str(user_id)] = data
    save_users(users)

def get_or_create_user(user_id, username, first_name):
    users = load_users()
    user_id_str = str(user_id)
    now = time.time()
    if user_id_str not in users:
        balance = random.randint(50, 100)
        users[user_id_str] = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "balance": balance,
            "total_spent": 0,
            "slaves": [],
            "sum_slaves": 0,
            "tasks": {
                "subscribe": False,
                "buy_first_slave": False,
                "first_replenish": False
            },
            "has_replenished": False,
            "blocked": False,
            "last_income_collect": now,
            "created_at": now,
            "shield_expires": 0,
            "level": 1,
            "level_up_start": 0,
            "description": "",
            "vip_expires": 0
        }
        save_users(users)
        return users[user_id_str], True
    else:
        user = users[user_id_str]
        # миграция
        if "tasks" not in user:
            user["tasks"] = {"subscribe": False, "buy_first_slave": False, "first_replenish": False}
        if "has_replenished" not in user:
            user["has_replenished"] = False
        if "blocked" not in user:
            user["blocked"] = False
        if "total_spent" not in user:
            user["total_spent"] = 0
        if "last_income_collect" not in user:
            user["last_income_collect"] = now
        if "created_at" not in user:
            user["created_at"] = now
        if "shield_expires" not in user:
            user["shield_expires"] = 0
        if "level" not in user:
            user["level"] = 1
        if "level_up_start" not in user:
            user["level_up_start"] = 0
        if "description" not in user:
            user["description"] = ""
        if "vip_expires" not in user:
            user["vip_expires"] = 0
        # Добавляем поле id для старых пользователей, чтобы работал значок разработчика
        if "id" not in user:
            user["id"] = user_id
        save_users(users)
        remove_self_enslavement(user_id)
        return users[user_id_str], False

def update_user_balance(user_id, amount):
    user_data = get_user(user_id)
    if user_data:
        user_data["balance"] += amount
        update_user(user_id, user_data)
        return user_data["balance"]
    return 0

def is_user_enslaved(user_id):
    users = load_users()
    for uid, data in users.items():
        if user_id in data.get("slaves", []):
            return True
    return False

def is_slave_on_market(slave_id):
    market = load_market()
    for data in market.values():
        if data["slave_id"] == slave_id:
            return True
    return False

# -------------------- ФУНКЦИИ ДЛЯ ПАССИВНОГО ДОХОДА --------------------
def get_slave_income(slave_data):
    level = slave_data.get("level", 1)
    base_income = level * level + 4
    if is_vip(slave_data):
        base_income *= 2
    return float(base_income)

def calculate_price(user_data):
    income = get_slave_income(user_data)
    level = user_data.get("level", 1)
    slaves_of_slave = len(user_data.get("slaves", []))
    vip_bonus = 50 if is_vip(user_data) else 0
    price = income * 5 + level * 5 + slaves_of_slave * 2 + vip_bonus
    return max(int(price), 25)

def calculate_total_income_rate(user_data):
    total = 0.0
    for slave_id in user_data.get("slaves", []):
        slave = get_user(slave_id)
        if slave:
            total += get_slave_income(slave)
    return total

def collect_income(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    now = time.time()
    last = user.get("last_income_collect", now)
    elapsed = min(now - last, MAX_INCOME_HOURS * 3600)
    hours = elapsed / 3600
    rate = calculate_total_income_rate(user)
    earned = int(rate * hours)
    if earned > 0:
        user["balance"] += earned
        user["last_income_collect"] = now
        update_user(user_id, user)
    return earned

# -------------------- ФУНКЦИИ ДЛЯ ПОДДЕРЖКИ --------------------
def load_support_requests():
    if os.path.exists(SUPPORT_REQUESTS_DB):
        with open(SUPPORT_REQUESTS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_support_requests(requests):
    with open(SUPPORT_REQUESTS_DB, "w", encoding="utf-8") as f:
        json.dump(requests, f, indent=4, ensure_ascii=False)

def create_ticket(user_id, username, problem_text, photo_id=None):
    tickets = load_support_requests()
    ticket_id = str(int(time.time())) + str(user_id)
    tickets[ticket_id] = {
        "user_id": user_id,
        "username": username,
        "problem": problem_text,
        "photo_id": photo_id,
        "status": "open",
        "created_at": time.time(),
        "admin_reply": None
    }
    save_support_requests(tickets)

    for admin_id in ADMIN_IDS:
        text = (f"📨 <b>Новый запрос в поддержку!</b>\n\n"
                f"👤 Пользователь: @{username}\n"
                f"🆔 ID: {user_id}\n"
                f"📝 Проблема: {problem_text}\n"
                f"🆔 Тикет: {ticket_id}")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💬 Ответить", callback_data=f"reply_ticket:{ticket_id}"))
        if photo_id:
            bot.send_photo(admin_id, photo_id, caption=text, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=markup)
    return ticket_id

def get_open_tickets():
    tickets = load_support_requests()
    return {k: v for k, v in tickets.items() if v["status"] == "open"}

# -------------------- ФУНКЦИИ ДЛЯ CRYPTOBOT --------------------
def create_invoice(asset, amount, description):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN}
    payload = {
        "asset": asset,
        "amount": amount,
        "description": description
    }
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    if data.get("ok"):
        return data["result"]
    else:
        raise Exception(data.get("error", "Error creating invoice"))

def get_invoice_status(invoice_id):
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN}
    params = {"invoice_ids": invoice_id}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    if data.get("ok") and data["result"]["items"]:
        return data["result"]["items"][0]["status"]
    return None

def check_payment_status(invoice_id, user_id, amount_rub, chat_id, message_id):
    start_time = time.time()
    while time.time() - start_time < 300:
        try:
            status = get_invoice_status(invoice_id)
            if status == 'paid':
                new_balance = update_user_balance(user_id, amount_rub)
                amount_usdt = amount_rub / RUB_TO_USDT_RATE
                success_text = (f"🎉 Ваш баланс успешно пополнен!\n"
                                f"💸 Сумма: {amount_rub} руб. ({amount_usdt:.2f} USDT)\n"
                                f"💰 Текущий баланс: {new_balance} монет")
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🏠 Домой", callback_data="back_to_menu"))
                bot.edit_message_text(success_text, chat_id=chat_id, message_id=message_id, reply_markup=markup)

                user_data = get_user(user_id)
                if user_data and not user_data.get("has_replenished"):
                    user_data["has_replenished"] = True
                    if not user_data["tasks"]["first_replenish"]:
                        user_data["tasks"]["first_replenish"] = True
                        user_data["balance"] += 50
                    update_user(user_id, user_data)
                    bot.send_message(chat_id, "🎉 Задание 'Пополнить баланс' выполнено! +50 монет.")
                return
            elif status == 'expired':
                bot.edit_message_text("⏳ Время оплаты истекло!", chat_id=chat_id, message_id=message_id)
                return
        except Exception as e:
            print(f"Ошибка проверки платежа: {e}")
        time.sleep(5)
    bot.edit_message_text("⏳ Время оплаты истекло!", chat_id=chat_id, message_id=message_id)

# -------------------- ФУНКЦИИ ДЛЯ ТОПОВ --------------------
def get_top_by_slaves():
    users = load_users()
    top = []
    for uid, data in users.items():
        if not data.get("blocked", False):
            name = get_display_name(data)
            top.append((int(uid), data.get("sum_slaves", 0), name))
    top.sort(key=lambda x: x[1], reverse=True)
    return top[:10]

def get_top_by_current_value():
    users = load_users()
    top = []
    for uid, data in users.items():
        if not data.get("blocked", False):
            total_value = 0
            for slave_id in data.get("slaves", []):
                slave = get_user(slave_id)
                if slave:
                    total_value += calculate_price(slave)
            if total_value > 0:
                name = get_display_name(data)
                top.append((int(uid), total_value, name))
    top.sort(key=lambda x: x[1], reverse=True)
    return top[:10]

def get_top_by_income():
    users = load_users()
    top = []
    for uid, data in users.items():
        if not data.get("blocked", False):
            income = calculate_total_income_rate(data)
            name = get_display_name(data)
            top.append((int(uid), income, name))
    top.sort(key=lambda x: x[1], reverse=True)
    return top[:10]

def get_top_by_balance():
    """Топ по общему балансу."""
    users = load_users()
    top = []
    for uid, data in users.items():
        if not data.get("blocked", False):
            balance = data.get("balance", 0)
            name = get_display_name(data)
            top.append((int(uid), balance, name))
    top.sort(key=lambda x: x[1], reverse=True)
    return top[:10]

def check_level_up(slave_id):
    slave = get_user(slave_id)
    if not slave:
        return
    start = slave.get("level_up_start", 0)
    if start > 0 and time.time() >= start:
        current_level = slave.get("level", 1)
        if current_level < MAX_SLAVE_LEVEL:
            slave["level"] = current_level + 1
            slave["level_up_start"] = 0
            update_user(slave_id, slave)

# -------------------- ГЛАВНОЕ МЕНЮ --------------------
def start_menu(chat_id, message_id=None, user_name="", user_id=None, balance=0, is_new=False):
    if is_new:
        welcome_text = (f"Привет, {user_name}!👋\n\n"
                        f"💰 Твой стартовый баланс: {balance} монет\n\n"
                        "Помнишь проект в вк, в котором ты мог брать\n"
                        "друзей в рабство за деньги?\n\n"
                        "Я решил перенести его в тг!\n\n"
                        "Тут почти тот-же самый функционал (может быть чуть лучше).\n\n"
                        "Купи своего первого раба уже сейчас!⬇")
    else:
        welcome_text = (f"👋 {user_name}, добро пожаловать!\n"
                        f"💰 Твой баланс: {balance} монет\n"
                        "Выбери действие:")
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [
        InlineKeyboardButton("📔 Задания", callback_data="tasks"),
        InlineKeyboardButton("👥 Ваши рабы", callback_data="your_rabs"),
        InlineKeyboardButton("💸 Пополнить", callback_data="replenish_menu"),
        InlineKeyboardButton("💰 Собрать доход", callback_data="collect_income"),
        InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        InlineKeyboardButton("📞 Поддержка", callback_data="support"),
        InlineKeyboardButton("⭐ Топ", callback_data="top_menu"),
        InlineKeyboardButton("🏪 Рынок", callback_data="market_menu"),
        InlineKeyboardButton("📈 Биржа", callback_data="stock_market"),
        InlineKeyboardButton("🔪 Кража", callback_data="steal_menu"),
        InlineKeyboardButton("🛡 Щит", callback_data="buy_shield")
    ]
    if user_id in ADMIN_IDS:
        buttons.append(InlineKeyboardButton("🔧 Админ панель", callback_data="admin_panel"))

    markup.row(buttons[0], buttons[2])
    markup.row(buttons[1], buttons[3])
    markup.row(buttons[6], buttons[7])
    markup.row(buttons[8], buttons[9], buttons[10])
    markup.row(buttons[4], buttons[5])
    if len(buttons) > 11:
        markup.row(buttons[11])

    if message_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=welcome_text, reply_markup=markup, parse_mode="HTML")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise
    else:
        bot.send_message(chat_id, welcome_text, reply_markup=markup, parse_mode="HTML")

# -------------------- ОБРАБОТЧИК /START --------------------
@bot.message_handler(commands=['start'])
def welcome_handler(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    user_data, is_new = get_or_create_user(user_id, username, first_name)
    if user_data.get("blocked"):
        bot.send_message(message.chat.id, "❌ Вы заблокированы в боте.")
        return
    balance = user_data["balance"]
    user_name = get_display_name(user_data)
    if is_new:
        bot.send_message(message.chat.id, f"🎉 Поздравляю! Ты получил стартовый баланс: {balance} монет!")
    start_menu(message.chat.id, user_id=user_id, user_name=user_name, balance=balance, is_new=is_new)

# -------------------- НАЗАД В ГЛАВНОЕ МЕНЮ --------------------
@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_data = get_user(user_id)
    if not user_data or user_data.get("blocked"):
        bot.answer_callback_query(call.id, "Ошибка")
        return
    balance = user_data["balance"]
    user_name = get_display_name(user_data)
    start_menu(chat_id, message_id=message_id, user_name=user_name, user_id=user_id, balance=balance, is_new=False)

# -------------------- ПРОФИЛЬ (добавлена строка о рабстве) --------------------
@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_data = get_user(user_id)
    if not user_data or user_data.get("blocked"):
        bot.answer_callback_query(call.id, "Ошибка")
        return

    top_slaves = get_top_by_slaves()
    position = 0
    for i, (uid, count, name) in enumerate(top_slaves, 1):
        if uid == user_id:
            position = i
            break
    if position == 0:
        position = "не в топе"

    income_rate = calculate_total_income_rate(user_data)
    reg_date = format_time(user_data.get("created_at", time.time()))
    shield_exp = get_shield_expires(user_data)
    shield_text = f"до {format_time(shield_exp)}" if shield_exp > time.time() else "нет"
    if is_developer(user_id):
        shield_text = "бесконечный (разработчик)"

    vip_status = "✅ Активен до " + format_time(user_data.get("vip_expires", 0)) if is_vip(user_data) and not is_developer(user_id) else "✅ (разработчик)" if is_developer(user_id) else "❌ Нет"

    # Определяем владельца
    owner_data = get_owner(user_id)
    if owner_data:
        owner_name = get_display_name(owner_data)
        owner_id = owner_data["id"]
        enslavement_text = f"👤 В рабстве у: {owner_name} (ID {owner_id})"
    else:
        enslavement_text = "👤 В рабстве у: нет"

    profile_text = (f"➖➖➖➖➖➖➖➖➖\n"
                    f"<b>Профиль игрока</b>\n"
                    f"👤 Имя: {get_display_name(user_data)}\n"
                    f"🆔 ID: {user_id}\n"
                    f"💰 Баланс: {user_data['balance']} монет\n"
                    f"💸 Потрачено всего: {user_data.get('total_spent',0)} монет\n"
                    f"👥 Количество рабов: {user_data.get('sum_slaves',0)}\n"
                    f"⏳ Доход в час: {income_rate:.1f} монет\n"
                    f"🏆 Место в топе (по рабам): {position}\n"
                    f"📅 Зарегистрирован: {reg_date}\n"
                    f"{enslavement_text}\n"
                    f"🛡 Щит от краж: {shield_text}\n"
                    f"💎 VIP статус: {vip_status}\n"
                    "➖➖➖➖➖➖➖➖➖")

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    try:
        bot.edit_message_text(profile_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

# -------------------- СБОР ДОХОДА --------------------
@bot.callback_query_handler(func=lambda call: call.data == "collect_income")
def collect_income_handler(call):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if not user_data:
        bot.answer_callback_query(call.id, "Ошибка")
        return
    earned = collect_income(user_id)
    rate = calculate_total_income_rate(user_data)
    if earned > 0:
        text = f"💰 Вы собрали {earned} монет!\nТекущий доход: {rate:.1f} монет/час."
    else:
        text = f"⌛ Пока не накопилось монет.\nТекущий доход: {rate:.1f} монет/час."
    bot.answer_callback_query(call.id, text, show_alert=True)
    back_to_menu_handler(call)

# -------------------- ТОП --------------------
@bot.callback_query_handler(func=lambda call: call.data == "top_menu")
def top_menu(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    text = "📊 Выберите тип топа:"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👥 По количеству рабов", callback_data="top_slaves"),
        InlineKeyboardButton("💰 По стоимости рабов", callback_data="top_value"),
        InlineKeyboardButton("⏳ По доходу в час", callback_data="top_income"),
        InlineKeyboardButton("💎 По балансу", callback_data="top_balance"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "top_slaves")
def top_slaves(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    top = get_top_by_slaves()
    text = "🏆 <b>Топ по количеству рабов</b>\n\n"
    for i, (uid, count, name) in enumerate(top, 1):
        text += f"{i}. {name} — {count} раб(ов)\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="top_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "top_value")
def top_value(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    top = get_top_by_current_value()
    text = "💰 <b>Топ по суммарной стоимости рабов</b>\n\n"
    if not top:
        text += "Пока никто не владеет рабами."
    else:
        for i, (uid, value, name) in enumerate(top, 1):
            text += f"{i}. {name} — {value} монет\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="top_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "top_income")
def top_income(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    top = get_top_by_income()
    text = "⏳ <b>Топ по доходу в час</b>\n\n"
    for i, (uid, income, name) in enumerate(top, 1):
        text += f"{i}. {name} — {income:.1f} монет/час\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="top_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "top_balance")
def top_balance(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    top = get_top_by_balance()
    text = "💎 <b>Топ по общему балансу</b>\n\n"
    for i, (uid, balance, name) in enumerate(top, 1):
        text += f"{i}. {name} — {balance} монет\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="top_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

# -------------------- ЗАДАНИЯ --------------------
@bot.callback_query_handler(func=lambda call: call.data == "tasks")
def tasks_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_data = get_user(user_id)
    if not user_data:
        bot.answer_callback_query(call.id, "Ошибка")
        return
    tasks = user_data.get("tasks", {})
    sub_emoji = "✅" if tasks.get("subscribe") else "❌"
    buy_emoji = "✅" if tasks.get("buy_first_slave") else "❌"
    replenish_emoji = "✅" if tasks.get("first_replenish") else "❌"
    text = ("📋 <b>Стартовые задания</b>\n"
            "Выполняя их, ты заработаешь монеты.\n"
            "✅ — выполнено, ❌ — не выполнено.\n\n"
            "🎁 Награда за каждое: +50 монет")
    markup = InlineKeyboardMarkup(row_width=1)
    buttons = []
    if not tasks.get("subscribe"):
        buttons.append(InlineKeyboardButton(f"{sub_emoji} Подписаться на канал", callback_data="task_subscribe"))
    else:
        buttons.append(InlineKeyboardButton(f"{sub_emoji} Подписаться на канал", callback_data="task_already_done"))
    if not tasks.get("buy_first_slave"):
        buttons.append(InlineKeyboardButton(f"{buy_emoji} Купить первого раба", callback_data="task_buy_first_slave"))
    else:
        buttons.append(InlineKeyboardButton(f"{buy_emoji} Купить первого раба", callback_data="task_already_done"))
    if not tasks.get("first_replenish"):
        buttons.append(InlineKeyboardButton(f"{replenish_emoji} Пополнить баланс", callback_data="task_replenish"))
    else:
        buttons.append(InlineKeyboardButton(f"{replenish_emoji} Пополнить баланс", callback_data="task_already_done"))
    buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    markup.add(*buttons)
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "task_subscribe")
def task_subscribe(call):
    user_id = call.from_user.id
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "administrator", "creator"]:
            user_data = get_user(user_id)
            if not user_data["tasks"]["subscribe"]:
                user_data["tasks"]["subscribe"] = True
                user_data["balance"] += 50
                update_user(user_id, user_data)
                bot.answer_callback_query(call.id, "✅ Задание выполнено! +50 монет")
                tasks_handler(call)
            else:
                bot.answer_callback_query(call.id, "Задание уже выполнено")
        else:
            bot.answer_callback_query(call.id, "❌ Вы не подписаны на канал. Подпишитесь и нажмите снова.", show_alert=True)
    except Exception as e:
        bot.answer_callback_query(call.id, "Ошибка: бот не администратор канала или канал не существует.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "task_buy_first_slave")
def task_buy_first_slave(call):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if len(user_data.get("slaves", [])) > 0:
        if not user_data["tasks"]["buy_first_slave"]:
            user_data["tasks"]["buy_first_slave"] = True
            user_data["balance"] += 50
            update_user(user_id, user_data)
            bot.answer_callback_query(call.id, "✅ Задание выполнено! +50 монет")
            tasks_handler(call)
        else:
            bot.answer_callback_query(call.id, "Задание уже выполнено")
    else:
        bot.answer_callback_query(call.id, "У вас нет рабов. Купите первого через '👥 Ваши рабы'.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "task_replenish")
def task_replenish(call):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if user_data.get("has_replenished", False):
        if not user_data["tasks"]["first_replenish"]:
            user_data["tasks"]["first_replenish"] = True
            user_data["balance"] += 50
            update_user(user_id, user_data)
            bot.answer_callback_query(call.id, "✅ Задание выполнено! +50 монет")
            tasks_handler(call)
        else:
            bot.answer_callback_query(call.id, "Задание уже выполнено")
    else:
        bot.answer_callback_query(call.id, "Вы ещё не пополняли баланс. Пополните через кнопку '💸 Пополнить'.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "task_already_done")
def task_already_done(call):
    bot.answer_callback_query(call.id, "Это задание уже выполнено", show_alert=False)

# -------------------- ВАШИ РАБЫ (ПОКУПКА/ПРОДАЖА/УПРАВЛЕНИЕ) --------------------
@bot.callback_query_handler(func=lambda call: call.data == "your_rabs")
def your_rabs_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_data = get_user(user_id)
    remove_self_enslavement(user_id)
    user_data = get_user(user_id)
    slaves = user_data.get("slaves", [])
    total_income = calculate_total_income_rate(user_data)
    if not slaves:
        text = "👥 У вас пока нет рабов. Хотите купить?"
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("💰 Купить раба", callback_data="buy_slave_menu"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
        )
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise
    else:
        text = f"📋 <b>Ваши рабы:</b> (общий доход: {total_income:.1f} монет/час)\n\n"
        for slave_id in slaves:
            slave_data = get_user(slave_id)
            if slave_data:
                name = get_display_name(slave_data)
                price = calculate_price(slave_data)
                income = get_slave_income(slave_data)
                level = slave_data.get("level", 1)
                desc = slave_data.get("description", "")
                desc_short = (desc[:20] + "...") if len(desc) > 20 else desc
                text += f"👤 {name} (ID {slave_id}) | Ур.{level} | Цена: {price} 💰 | Доход: {income:.1f}/ч"
                if desc:
                    text += f"\n   📝 {desc_short}"
                text += "\n"
        text += "\nВыберите раба для управления."
        markup = InlineKeyboardMarkup(row_width=2)
        for slave_id in slaves:
            slave_data = get_user(slave_id)
            if slave_data:
                name = get_display_name(slave_data)
                markup.add(InlineKeyboardButton(f"⚙️ {name}", callback_data=f"manage_slave_{slave_id}"))
        markup.add(
            InlineKeyboardButton("💰 Купить нового", callback_data="buy_slave_menu"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
        )
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_slave_") and call.data.split("_")[2].isdigit())
def manage_slave(call):
    slave_id = int(call.data.split("_")[2])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб вам не принадлежит.")
        return
    slave_data = get_user(slave_id)
    if not slave_data:
        bot.answer_callback_query(call.id, "Ошибка данных раба.")
        return

    check_level_up(slave_id)
    slave_data = get_user(slave_id)

    level_up_start = slave_data.get("level_up_start", 0)
    level_up_text = ""
    if level_up_start > 0:
        remaining = int(level_up_start - time.time())
        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            level_up_text = f"\n⏳ Идёт прокачка до уровня {slave_data.get('level',1)+1}. Осталось: {hours}ч {minutes}м."

    name = get_display_name(slave_data)
    level = slave_data.get("level", 1)
    price = calculate_price(slave_data)
    income = get_slave_income(slave_data)
    desc = slave_data.get("description", "нет")

    cost_info = ""
    if level < MAX_SLAVE_LEVEL:
        cost = int(LEVEL_UP_BASE_COST * (LEVEL_UP_COST_MULTIPLIER ** (level - 1)))
        duration = LEVEL_UP_BASE_TIME * (LEVEL_UP_TIME_MULTIPLIER ** (level - 1))
        duration_hours = int(duration // 3600)
        cost_info = f"\n⚡ Прокачка до ур.{level+1}: {cost} монет, {duration_hours} ч."
    else:
        cost_info = "\n⭐ Максимальный уровень достигнут."

    text = (f"👤 <b>{name}</b> (ID {slave_id})\n"
            f"⭐ Уровень: {level}\n"
            f"💰 Цена: {price} монет\n"
            f"📈 Доход: {income:.1f} монет/час\n"
            f"📝 Описание: {desc}"
            f"{cost_info}"
            f"{level_up_text}")

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚡ Прокачать", callback_data=f"levelup_{slave_id}"),
        InlineKeyboardButton("✏️ Описание", callback_data=f"setdesc_{slave_id}")
    )
    markup.add(
        InlineKeyboardButton("🏷 Продать", callback_data=f"sell_{slave_id}"),
        InlineKeyboardButton("📤 На рынок", callback_data=f"market_sell_{slave_id}")
    )
    markup.add(
        InlineKeyboardButton("🎁 Подарить", callback_data=f"gift_{slave_id}"),
        InlineKeyboardButton("⬅️ Назад", callback_data="your_rabs")
    )

    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

# -------------------- ПРОКАЧКА РАБА --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("levelup_") and call.data.split("_")[1].isdigit())
def levelup_slave(call):
    slave_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб вам не принадлежит.")
        return
    slave_data = get_user(slave_id)
    if not slave_data:
        bot.answer_callback_query(call.id, "Ошибка данных раба.")
        return

    check_level_up(slave_id)
    slave_data = get_user(slave_id)
    current_level = slave_data.get("level", 1)
    if current_level >= MAX_SLAVE_LEVEL:
        bot.answer_callback_query(call.id, "Раб уже достиг максимального уровня!")
        return

    if slave_data.get("level_up_start", 0) > 0:
        remaining = int(slave_data["level_up_start"] - time.time())
        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            bot.answer_callback_query(call.id, f"Прокачка уже идёт! Осталось {hours}ч {minutes}м.", show_alert=True)
            return

    cost = int(LEVEL_UP_BASE_COST * (LEVEL_UP_COST_MULTIPLIER ** (current_level - 1)))
    if user_data["balance"] < cost:
        bot.answer_callback_query(call.id, f"Недостаточно монет. Нужно {cost}.", show_alert=True)
        return

    user_data["balance"] -= cost
    duration = LEVEL_UP_BASE_TIME * (LEVEL_UP_TIME_MULTIPLIER ** (current_level - 1))
    slave_data["level_up_start"] = time.time() + duration
    update_user(user_id, user_data)
    update_user(slave_id, slave_data)

    def level_up_complete():
        time.sleep(duration + 1)
        check_level_up(slave_id)
        try:
            bot.send_message(user_id, f"🎉 Ваш раб {slave_data['first_name']} достиг уровня {current_level+1}!")
        except:
            pass
    threading.Thread(target=level_up_complete, daemon=True).start()

    bot.answer_callback_query(call.id, f"Прокачка началась! Уровень {current_level+1} будет достигнут через {int(duration//3600)} ч.")
    manage_slave(call)

# -------------------- УСТАНОВКА ОПИСАНИЯ РАБА --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("setdesc_") and call.data.split("_")[1].isdigit())
def setdesc_slave(call):
    slave_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб вам не принадлежит.")
        return
    msg = bot.send_message(call.message.chat.id, "Введите новое описание для раба (до 200 символов):")
    user_states[user_id] = {"state": "waiting_slave_description", "slave_id": slave_id, "msg_id": msg.message_id}
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get("state") == "waiting_slave_description")
def process_slave_description(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    slave_id = state["slave_id"]
    try:
        bot.delete_message(message.chat.id, state["msg_id"])
    except:
        pass
    desc = message.text.strip()[:200]
    slave_data = get_user(slave_id)
    if not slave_data:
        bot.send_message(message.chat.id, "Ошибка: раб не найден.")
        del user_states[user_id]
        return
    slave_data["description"] = desc
    update_user(slave_id, slave_data)
    bot.send_message(message.chat.id, f"✅ Описание раба обновлено.")
    del user_states[user_id]
    fake_call = types.CallbackQuery(
        id="fake",
        from_user=message.from_user,
        chat_instance="0",
        message=message,
        data=f"manage_slave_{slave_id}",
        json_string="{}"
    )
    manage_slave(fake_call)

# -------------------- ПОКУПКА РАБА (СТОКОВЫЙ РЫНОК) --------------------
@bot.callback_query_handler(func=lambda call: call.data == "stock_market")
def stock_market(call):
    buy_slave_menu(call)

@bot.callback_query_handler(func=lambda call: call.data == "buy_slave_menu")
def buy_slave_menu(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_data = get_user(user_id)
    my_slaves = set(user_data.get("slaves", []))
    users = load_users()
    available = []
    for uid, data in users.items():
        uid_int = int(uid)
        if (uid_int != user_id and 
            not data.get("blocked") and 
            uid_int not in my_slaves and
            not is_user_enslaved(uid_int)):
            price = calculate_price(data)
            income = get_slave_income(data)
            name = get_display_name(data)
            available.append((uid_int, name, price, income))
    if not available:
        text = "❌ Нет доступных пользователей для покупки."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise
        return
    text = "💰 <b>Выберите пользователя для покупки (свободные рабы):</b>\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for uid, name, price, income in available[:10]:
        markup.add(InlineKeyboardButton(
            f"{name} | Цена: {price} 💰 | Доход: {income:.1f}/ч", 
            callback_data=f"buy_{uid}"
        ))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_") and call.data.split("_")[1].isdigit())
def confirm_buy(call):
    target_id = int(call.data.split("_")[1])
    buyer_id = call.from_user.id
    buyer_data = get_user(buyer_id)
    target_data = get_user(target_id)

    if not target_data or target_data.get("blocked"):
        bot.answer_callback_query(call.id, "Пользователь недоступен")
        return

    if target_id == buyer_id:
        bot.answer_callback_query(call.id, "❌ Вы не можете купить самого себя!", show_alert=True)
        return

    if is_user_enslaved(target_id):
        bot.answer_callback_query(call.id, "❌ Этот пользователь уже куплен другим игроком.", show_alert=True)
        return

    price = calculate_price(target_data)
    if buyer_data["balance"] >= price:
        buyer_data["balance"] -= price
        buyer_data["total_spent"] = buyer_data.get("total_spent", 0) + price
        buyer_data["slaves"].append(target_id)
        buyer_data["sum_slaves"] = len(buyer_data["slaves"])
        update_user(buyer_id, buyer_data)

        # Уведомление рабу
        try:
            buyer_name = get_display_name(buyer_data)
            bot.send_message(target_id, f"🔗 Вас купил игрок {buyer_name} (ID {buyer_id}) за {price} монет.")
        except:
            pass

        bot.answer_callback_query(call.id, f"✅ Вы купили {get_display_name(target_data)} за {price} монет!")
        if not buyer_data["tasks"]["buy_first_slave"] and len(buyer_data["slaves"]) == 1:
            buyer_data["tasks"]["buy_first_slave"] = True
            buyer_data["balance"] += 50
            update_user(buyer_id, buyer_data)
            bot.send_message(call.message.chat.id, "🎉 Задание 'Купить первого раба' выполнено! +50 монет.")
        back_to_menu_handler(call)
    else:
        bot.answer_callback_query(call.id, f"❌ Недостаточно монет. Нужно {price}.", show_alert=True)

# -------------------- ПРОДАЖА РАБА (МГНОВЕННАЯ) --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("sell_") and call.data.split("_")[1].isdigit())
def confirm_sell(call):
    slave_id = int(call.data.split("_")[1])
    owner_id = call.from_user.id
    owner_data = get_user(owner_id)
    if slave_id not in owner_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб уже не ваш.")
        return
    if is_slave_on_market(slave_id):
        bot.answer_callback_query(call.id, "Этот раб уже выставлен на рынке. Сначала снимите его с продажи.", show_alert=True)
        return
    slave_data = get_user(slave_id)
    price = calculate_price(slave_data)
    owner_data["slaves"].remove(slave_id)
    owner_data["sum_slaves"] = len(owner_data["slaves"])
    owner_data["balance"] += price
    update_user(owner_id, owner_data)

    # Уведомление рабу
    try:
        bot.send_message(slave_id, f"ℹ️ Ваш владелец продал вас системе за {price} монет. Теперь вы свободны (пока вас снова не купят).")
    except:
        pass

    bot.answer_callback_query(call.id, f"✅ Вы продали раба за {price} монет!")
    your_rabs_handler(call)

# -------------------- РЫНОК (ПОЛЬЗОВАТЕЛЬСКИЙ) --------------------
@bot.callback_query_handler(func=lambda call: call.data == "market_menu")
def market_menu(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    text = "🏪 <b>Рынок рабов</b>\n\nЗдесь вы можете купить или выставить на продажу рабов по своей цене."
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🛒 Купить раба", callback_data="market_buy"),
        InlineKeyboardButton("📤 Выставить на продажу", callback_data="market_sell"),
        InlineKeyboardButton("📋 Мои лоты", callback_data="market_my_offers"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "market_buy")
def market_buy(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    offers = get_market_offers()
    if not offers:
        text = "На рынке пока нет предложений."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="market_menu"))
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise
        return
    text = "🛒 <b>Рабы на продажу:</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for offer in offers:
        seller_data = get_user(offer["seller_id"])
        seller_name = get_display_name(seller_data) if seller_data else "Unknown"
        text += (f"👤 {offer['slave_name']} (ID {offer['slave_id']})\n"
                 f"💰 Цена: {offer['price']} (рыночная: {offer['slave_price']})\n"
                 f"📈 Доход: {offer['income']:.1f}/ч\n"
                 f"🧑 Продавец: {seller_name}\n\n")
        markup.add(InlineKeyboardButton(
            f"Купить {offer['slave_name']} за {offer['price']}", 
            callback_data=f"market_buyoffer_{offer['offer_id']}"
        ))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="market_menu"))
    if len(text) > 4000:
        bot.send_message(chat_id, text[:4000], parse_mode="HTML")
        bot.send_message(chat_id, text[4000:], parse_mode="HTML", reply_markup=markup)
    else:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("market_buyoffer_") and call.data.split("_")[2].isdigit())
def market_buy_offer(call):
    offer_id = call.data.split("_")[2]
    buyer_id = call.from_user.id
    market = load_market()
    if offer_id not in market:
        bot.answer_callback_query(call.id, "❌ Предложение не найдено.")
        return
    offer = market[offer_id]
    seller_id = offer["seller_id"]
    slave_id = offer["slave_id"]
    price = offer["price"]
    buyer_data = get_user(buyer_id)
    seller_data = get_user(seller_id)
    slave_data = get_user(slave_id)

    if not buyer_data or not seller_data or not slave_data:
        bot.answer_callback_query(call.id, "❌ Ошибка данных.")
        return
    if buyer_id == seller_id:
        bot.answer_callback_query(call.id, "❌ Нельзя купить своего же раба.")
        return
    if buyer_id == slave_id:
        bot.answer_callback_query(call.id, "❌ Нельзя купить самого себя.")
        return
    if slave_id not in seller_data.get("slaves", []):
        bot.answer_callback_query(call.id, "❌ Продавец уже не владеет этим рабом.")
        remove_market_offer(offer_id)
        return
    if buyer_data["balance"] < price:
        bot.answer_callback_query(call.id, f"❌ Недостаточно монет. Нужно {price}.", show_alert=True)
        return

    buyer_data["balance"] -= price
    buyer_data["total_spent"] = buyer_data.get("total_spent", 0) + price
    buyer_data["slaves"].append(slave_id)
    buyer_data["sum_slaves"] = len(buyer_data["slaves"])
    seller_data["slaves"].remove(slave_id)
    seller_data["sum_slaves"] = len(seller_data["slaves"])
    seller_data["balance"] += price
    update_user(buyer_id, buyer_data)
    update_user(seller_id, seller_data)
    remove_market_offer(offer_id)

    buyer_name = get_display_name(buyer_data)
    try:
        bot.send_message(slave_id, f"🔗 Вас купил на рынке игрок {buyer_name} (ID {buyer_id}) за {price} монет.")
    except:
        pass
    try:
        bot.send_message(seller_id, f"💰 Ваш раб {get_display_name(slave_data)} продан на рынке за {price} монет!")
    except:
        pass

    bot.answer_callback_query(call.id, f"✅ Вы купили раба {get_display_name(slave_data)} за {price} монет!")
    market_buy(call)

@bot.callback_query_handler(func=lambda call: call.data == "market_sell")
def market_sell(call):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    slaves = user_data.get("slaves", [])
    available = [s for s in slaves if not is_slave_on_market(s)]
    if not available:
        bot.answer_callback_query(call.id, "У вас нет рабов для выставления на рынок.", show_alert=True)
        return
    text = "📤 <b>Выберите раба для выставления на рынок:</b>\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for slave_id in available:
        slave_data = get_user(slave_id)
        if slave_data:
            name = get_display_name(slave_data)
            markup.add(InlineKeyboardButton(name, callback_data=f"market_sell_{slave_id}"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="market_menu"))
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("market_sell_") and call.data.split("_")[2].isdigit())
def market_sell_choose(call):
    slave_id = int(call.data.split("_")[2])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб не ваш.")
        return
    if is_slave_on_market(slave_id):
        bot.answer_callback_query(call.id, "Этот раб уже на рынке.")
        return
    slave_data = get_user(slave_id)
    market_price = calculate_price(slave_data)
    text = (f"Выставляем раба: {get_display_name(slave_data)}\n"
            f"Рыночная цена: {market_price}\n\n"
            f"Введите цену продажи (целое число):")
    msg = bot.send_message(call.message.chat.id, text)
    user_states[user_id] = {"state": "waiting_market_price", "slave_id": slave_id, "msg_id": msg.message_id}
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get("state") == "waiting_market_price")
def process_market_price(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = user_states[user_id]
    try:
        bot.delete_message(chat_id, state["msg_id"])
    except:
        pass
    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except:
        msg = bot.send_message(chat_id, "❌ Введите целое положительное число.")
        user_states[user_id]["msg_id"] = msg.message_id
        return
    slave_id = state["slave_id"]
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.send_message(chat_id, "❌ Вы больше не владеете этим рабом.")
        del user_states[user_id]
        return
    if is_slave_on_market(slave_id):
        bot.send_message(chat_id, "❌ Этот раб уже на рынке.")
        del user_states[user_id]
        return
    add_market_offer(user_id, slave_id, price)
    bot.send_message(chat_id, f"✅ Раб выставлен на рынок за {price} монет.")
    del user_states[user_id]
    fake_call = types.CallbackQuery(
        id="fake",
        from_user=message.from_user,
        chat_instance="0",
        message=message,
        data="market_menu",
        json_string="{}"
    )
    market_menu(fake_call)

@bot.callback_query_handler(func=lambda call: call.data == "market_my_offers")
def market_my_offers(call):
    user_id = call.from_user.id
    offers = get_user_offers(user_id)
    if not offers:
        text = "У вас нет активных лотов."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="market_menu"))
        try:
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise
        return
    text = "📋 <b>Ваши лоты на рынке:</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for offer in offers:
        text += f"👤 {offer['slave_name']} | Цена: {offer['price']}\n"
        markup.add(InlineKeyboardButton(
            f"❌ Снять с продажи {offer['slave_name']}", 
            callback_data=f"market_remove_{offer['offer_id']}"
        ))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="market_menu"))
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("market_remove_") and call.data.split("_")[2].isdigit())
def market_remove_offer(call):
    user_id = call.from_user.id
    offer_id = call.data.split("_")[2]
    market = load_market()
    if offer_id not in market:
        bot.answer_callback_query(call.id, "Лот не найден.")
        return
    if market[offer_id]["seller_id"] != user_id:
        bot.answer_callback_query(call.id, "Это не ваш лот.")
        return
    remove_market_offer(offer_id)
    bot.answer_callback_query(call.id, "✅ Лот снят с продажи.")
    market_my_offers(call)

# -------------------- КРАЖА РАБОВ (ИСПРАВЛЕНА) --------------------
@bot.callback_query_handler(func=lambda call: call.data == "steal_menu")
def steal_menu(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_data = get_user(user_id)

    users = load_users()
    owners = {}
    for uid, data in users.items():
        uid_int = int(uid)
        if data.get("blocked") or uid_int == user_id:
            continue
        if len(data.get("slaves", [])) == 0:
            continue
        shield_exp = get_shield_expires(data)
        if shield_exp > time.time():
            continue
        owners[uid_int] = data

    if not owners:
        text = "😕 Сейчас нет владельцев, у которых можно украсть рабов (все под щитом или нет рабов)."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise
        return

    text = "🔪 <b>Выберите владельца, у которого хотите украсть раба:</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for owner_id, owner_data in owners.items():
        owner_name = get_display_name(owner_data)
        slaves_count = len(owner_data.get("slaves", []))
        text += f"👤 {owner_name} (ID {owner_id}) | Рабов: {slaves_count}\n"
        markup.add(InlineKeyboardButton(f"У {owner_name}", callback_data=f"steal_owner_{owner_id}"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    if len(text) > 4000:
        bot.send_message(chat_id, text[:4000], parse_mode="HTML")
        bot.send_message(chat_id, text[4000:], parse_mode="HTML", reply_markup=markup)
    else:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("steal_owner_") and call.data.split("_")[2].isdigit())
def steal_owner_choice(call):
    owner_id = int(call.data.split("_")[2])
    thief_id = call.from_user.id
    thief_data = get_user(thief_id)
    owner_data = get_user(owner_id)
    if not owner_data or owner_data.get("blocked"):
        bot.answer_callback_query(call.id, "Владелец не найден или заблокирован.")
        return
    shield_exp = get_shield_expires(owner_data)
    if shield_exp > time.time():
        bot.answer_callback_query(call.id, "❌ У этого владельца активен щит! Украсть нельзя.", show_alert=True)
        return
    slaves = owner_data.get("slaves", [])
    if not slaves:
        bot.answer_callback_query(call.id, "У этого владельца больше нет рабов.")
        return

    # Фильтруем рабов: нельзя украсть себя, раба, который на рынке, и раба, который является самим вором
    valid_slaves = []
    for slave_id in slaves:
        if slave_id == thief_id:
            continue  # нельзя украсть себя
        if is_slave_on_market(slave_id):
            continue
        valid_slaves.append(slave_id)

    if not valid_slaves:
        bot.answer_callback_query(call.id, "Нет доступных для кражи рабов (возможно, они на рынке или вы пытаетесь украсть себя).", show_alert=True)
        return

    text = f"🔪 <b>Выберите раба для кражи у {get_display_name(owner_data)}:</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for slave_id in valid_slaves:
        slave_data = get_user(slave_id)
        if slave_data:
            name = get_display_name(slave_data)
            level = slave_data.get("level", 1)
            income = get_slave_income(slave_data)
            cost = max(STEAL_BASE_COST, int(income * STEAL_COST_INCOME_MULTIPLIER))
            chance = max(0.1, STEAL_BASE_CHANCE - (level - 1) * STEAL_LEVEL_REDUCTION)
            if is_vip(thief_data):
                chance += STEAL_VIP_BONUS
                chance = min(1.0, chance)
            text += f"👤 {name} (ур.{level}) | Доход: {income:.1f}/ч\n💰 Стоимость: {cost} | Шанс: {int(chance*100)}%\n\n"
            markup.add(InlineKeyboardButton(f"Украсть {name}", callback_data=f"steal_slave_{slave_id}_{owner_id}"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="steal_menu"))
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("steal_slave_") and len(call.data.split("_")) == 4 and call.data.split("_")[2].isdigit() and call.data.split("_")[3].isdigit())
def process_steal(call):
    parts = call.data.split("_")
    slave_id = int(parts[2])
    owner_id = int(parts[3])
    thief_id = call.from_user.id
    thief_data = get_user(thief_id)
    owner_data = get_user(owner_id)
    slave_data = get_user(slave_id)

    if not thief_data or not owner_data or not slave_data:
        bot.answer_callback_query(call.id, "Ошибка данных.")
        return

    # Защита от кражи самого себя
    if thief_id == owner_id:
        bot.answer_callback_query(call.id, "❌ Нельзя украсть раба у самого себя.", show_alert=True)
        return
    if thief_id == slave_id:
        bot.answer_callback_query(call.id, "❌ Нельзя украсть самого себя.", show_alert=True)
        return
    if owner_id == slave_id:
        bot.answer_callback_query(call.id, "❌ Раб не может быть владельцем.", show_alert=True)
        return

    if slave_id not in owner_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб уже не принадлежит указанному владельцу.")
        return

    # Проверка щита
    shield_exp = get_shield_expires(owner_data)
    if shield_exp > time.time():
        bot.answer_callback_query(call.id, "❌ Владелец защищён щитом от краж!", show_alert=True)
        return

    # Проверка, что раб не на рынке
    if is_slave_on_market(slave_id):
        bot.answer_callback_query(call.id, "❌ Этот раб выставлен на рынок и не может быть украден.", show_alert=True)
        return

    income = get_slave_income(slave_data)
    level = slave_data.get("level", 1)
    cost = max(STEAL_BASE_COST, int(income * STEAL_COST_INCOME_MULTIPLIER))
    if thief_data["balance"] < cost:
        bot.answer_callback_query(call.id, f"❌ Недостаточно монет. Нужно {cost}.", show_alert=True)
        return

    # Списываем деньги ДО попытки
    thief_data["balance"] -= cost
    update_user(thief_id, thief_data)

    chance = max(0.1, STEAL_BASE_CHANCE - (level - 1) * STEAL_LEVEL_REDUCTION)
    if is_vip(thief_data):
        chance += STEAL_VIP_BONUS
        chance = min(1.0, chance)
    success = random.random() < chance

    if success:
        owner_data["slaves"].remove(slave_id)
        owner_data["sum_slaves"] = len(owner_data["slaves"])
        thief_data["slaves"].append(slave_id)
        thief_data["sum_slaves"] = len(thief_data["slaves"])
        update_user(owner_id, owner_data)
        update_user(thief_id, thief_data)

        thief_name = get_display_name(thief_data)
        slave_name = get_display_name(slave_data)

        try:
            bot.send_message(owner_id, f"😱 Вашего раба {slave_name} украл игрок {thief_name}!")
        except:
            pass
        try:
            bot.send_message(thief_id, f"🎉 Вы успешно украли раба {slave_name}!")
        except:
            pass
        try:
            bot.send_message(slave_id, f"⚠️ Вас украл игрок {thief_name} (ID {thief_id}). Теперь вы его раб.")
        except:
            pass

        bot.answer_callback_query(call.id, f"✅ Успех! Раб {slave_name} теперь ваш!", show_alert=True)
    else:
        try:
            bot.send_message(owner_id, f"⚠️ Игрок {get_display_name(thief_data)} пытался украсть вашего раба {get_display_name(slave_data)}, но потерпел неудачу.")
        except:
            pass
        bot.answer_callback_query(call.id, f"❌ Попытка кражи провалилась! Вы потеряли {cost} монет.", show_alert=True)

    back_to_menu_handler(call)

# -------------------- ПОКУПКА ЩИТА --------------------
@bot.callback_query_handler(func=lambda call: call.data == "buy_shield")
def buy_shield_menu(call):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if has_permanent_shield(user_id):
        bot.answer_callback_query(call.id, "🔧 Как разработчик, вы имеете бесконечный щит!", show_alert=True)
        return
    income_rate = calculate_total_income_rate(user_data)
    text = "🛡 <b>Покупка щита от краж</b>\n\n"
    text += f"Ваш текущий доход: {income_rate:.1f} монет/час.\n"
    text += "Цена щита зависит от вашего дохода (чем выше доход, тем дороже).\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for hours, base_price in SHIELD_PRICES.items():
        multiplier = 1 + income_rate / 100.0
        final_price = int(base_price * multiplier)
        if hours == 24:
            desc = "24 часа"
        elif hours == 72:
            desc = "3 дня"
        elif hours == 168:
            desc = "7 дней"
        markup.add(InlineKeyboardButton(f"{desc} — {final_price} монет", callback_data=f"shield_{hours}"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("shield_"))
def process_shield_purchase(call):
    hours = int(call.data.split("_")[1])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if has_permanent_shield(user_id):
        bot.answer_callback_query(call.id, "🔧 У вас уже бесконечный щит разработчика!", show_alert=True)
        return
    income_rate = calculate_total_income_rate(user_data)
    base_price = SHIELD_PRICES[hours]
    multiplier = 1 + income_rate / 100.0
    price = int(base_price * multiplier)

    if user_data["balance"] < price:
        bot.answer_callback_query(call.id, f"Недостаточно монет. Нужно {price}.", show_alert=True)
        return
    user_data["balance"] -= price
    current_shield = user_data.get("shield_expires", 0)
    now = time.time()
    if current_shield > now:
        user_data["shield_expires"] = current_shield + hours * 3600
    else:
        user_data["shield_expires"] = now + hours * 3600
    update_user(user_id, user_data)
    bot.answer_callback_query(call.id, f"✅ Щит активирован на {hours} часов!", show_alert=True)
    back_to_menu_handler(call)

# -------------------- МЕНЮ ПОПОЛНЕНИЯ --------------------
@bot.callback_query_handler(func=lambda call: call.data == "replenish_menu")
def replenish_menu_handler(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    text = "💸 <b>Выберите способ пополнения:</b>"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("💎 Пополнить через CryptoBot (USDT)", callback_data="replenish"))
    markup.add(InlineKeyboardButton("⭐️ Пополнить через Telegram Stars", callback_data="replenish_stars"))
    markup.add(InlineKeyboardButton("💎 Купить VIP (150 ⭐)", callback_data="buy_vip"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

# -------------------- ПОПОЛНЕНИЕ ЧЕРЕЗ CRYPTOBOT --------------------
@bot.callback_query_handler(func=lambda call: call.data == "replenish")
def replenish_handler(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    text = "💸 Введите сумму пополнения в рублях (от 1 рубля):"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="replenish_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise
    user_states[call.from_user.id] = {"state": "waiting_replenish_amount", "msg_id": message_id}

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get("state") == "waiting_replenish_amount")
def process_replenish_amount(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = user_states[user_id]
    try:
        bot.delete_message(chat_id, state["msg_id"])
    except:
        pass
    try:
        amount_rub = int(message.text.strip())
        if amount_rub <= 0:
            raise ValueError
    except:
        msg = bot.send_message(chat_id, "❌ Введите положительное число (рубли).")
        user_states[user_id] = {"state": "waiting_replenish_amount", "msg_id": msg.message_id}
        return
    amount_usdt = amount_rub / RUB_TO_USDT_RATE
    if amount_usdt < 0.01:
        bot.send_message(chat_id, "❌ Минимальная сумма пополнения 1 рубль.")
        return
    try:
        invoice = create_invoice("USDT", amount_usdt, f"Пополнение баланса на {amount_rub} руб.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка создания счета: {e}")
        return
    text = (f"💳 Для пополнения на {amount_rub} руб. переведите {amount_usdt:.2f} USDT по ссылке:\n"
            f"{invoice['pay_url']}\n\n"
            f"⏰ Счёт действителен 5 минут.")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Оплатить", url=invoice['pay_url']))
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="replenish_menu"))
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup)
    threading.Thread(target=check_payment_status, args=(invoice['invoice_id'], user_id, amount_rub, chat_id, sent_msg.message_id), daemon=True).start()
    del user_states[user_id]

# -------------------- ПОПОЛНЕНИЕ ЧЕРЕЗ STARS --------------------
@bot.callback_query_handler(func=lambda call: call.data == "replenish_stars")
def replenish_stars_handler(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    text = "⭐️ <b>Пополнение через Telegram Stars</b>\n\nВыберите количество звезд для покупки монет:\n(Курс: 1 ⭐ = 1 монета)"
    markup = InlineKeyboardMarkup(row_width=2)
    for amount in SUGGESTED_STAR_AMOUNTS:
        markup.add(InlineKeyboardButton(f"{amount} ⭐", callback_data=f"pay_stars_{amount}"))
    markup.add(InlineKeyboardButton("✏️ Ввести свою сумму", callback_data="pay_stars_custom"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="replenish_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_stars_"))
def handle_stars_payment(call):
    data = call.data.split("_")
    if data[2] == "custom":
        msg = bot.send_message(call.message.chat.id, "✏️ Введите желаемое количество звезд (целое положительное число):")
        bot.register_next_step_handler(msg, process_custom_stars_amount)
        bot.answer_callback_query(call.id)
        return
    amount = int(data[2])
    create_stars_invoice(call.from_user.id, call.message.chat.id, amount, "stars_replenish")
    bot.answer_callback_query(call.id)

def process_custom_stars_amount(message):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной.")
        create_stars_invoice(message.from_user.id, message.chat.id, amount, "stars_replenish")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Пожалуйста, введите целое положительное число.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")

def create_stars_invoice(user_id, chat_id, stars_amount, purpose="stars_replenish"):
    prices = [types.LabeledPrice(label=f"{stars_amount} ⭐", amount=stars_amount)]
    title = "Пополнение баланса" if purpose == "stars_replenish" else "VIP подписка"
    description = f"Покупка {stars_amount} монет" if purpose == "stars_replenish" else "VIP статус на 30 дней"
    payload = f"{purpose}_{stars_amount}_{user_id}"
    provider_token = ""
    currency = "XTR"
    bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        invoice_payload=payload,
        provider_token=provider_token,
        currency=currency,
        prices=prices
    )

# -------------------- ПОКУПКА VIP --------------------
@bot.callback_query_handler(func=lambda call: call.data == "buy_vip")
def buy_vip_handler(call):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if is_vip(user_data):
        bot.answer_callback_query(call.id, "У вас уже активен VIP статус!", show_alert=True)
        return
    create_stars_invoice(user_id, call.message.chat.id, VIP_PRICE_STARS, "buy_vip")
    bot.answer_callback_query(call.id)

# -------------------- ОБРАБОТЧИКИ STARS ПЛАТЕЖЕЙ --------------------
@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    payment_info = message.successful_payment
    payload = payment_info.invoice_payload
    if payload.startswith("stars_replenish_"):
        parts = payload.split('_')
        stars_paid = int(parts[2])
        user_id = int(parts[3])
        coins_to_add = stars_paid * STARS_TO_COINS_RATE
        new_balance = update_user_balance(user_id, coins_to_add)
        user_data = get_user(user_id)
        if user_data and not user_data.get("has_replenished"):
            user_data["has_replenished"] = True
            if not user_data["tasks"]["first_replenish"]:
                user_data["tasks"]["first_replenish"] = True
                user_data["balance"] += 50
                bot.send_message(message.chat.id, "🎉 Задание 'Пополнить баланс' выполнено! +50 монет.")
            update_user(user_id, user_data)
        bot.send_message(
            message.chat.id,
            f"✅ Оплата прошла успешно!\n"
            f"Вы пополнили баланс на {coins_to_add} монет.\n"
            f"💰 Текущий баланс: {new_balance} монет."
        )
    elif payload.startswith("buy_vip_"):
        parts = payload.split('_')
        stars_paid = int(parts[2])
        user_id = int(parts[3])
        user_data = get_user(user_id)
        if is_vip(user_data):
            bot.send_message(message.chat.id, "У вас уже есть VIP!")
            return
        user_data["vip_expires"] = time.time() + VIP_DURATION_DAYS * 24 * 3600
        update_user(user_id, user_data)
        bot.send_message(
            message.chat.id,
            f"🎉 Поздравляем! Вы приобрели VIP статус на {VIP_DURATION_DAYS} дней!\n"
            f"Теперь вы получаете удвоенный доход от рабов, увеличенный шанс кражи и звёздочку рядом с именем."
        )

# -------------------- ДАРЕНИЕ РАБА --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("gift_") and call.data.split("_")[1].isdigit())
def gift_slave_start(call):
    slave_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.answer_callback_query(call.id, "Этот раб вам не принадлежит.")
        return
    msg = bot.send_message(call.message.chat.id, "Введите ID пользователя, которому хотите подарить раба:")
    user_states[user_id] = {"state": "waiting_gift_recipient", "slave_id": slave_id, "msg_id": msg.message_id}
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get("state") == "waiting_gift_recipient")
def process_gift_recipient(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    slave_id = state["slave_id"]
    try:
        bot.delete_message(message.chat.id, state["msg_id"])
    except:
        pass
    try:
        recipient_id = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❌ Некорректный ID. Попробуйте снова.")
        del user_states[user_id]
        return
    if recipient_id == user_id:
        bot.send_message(message.chat.id, "❌ Нельзя подарить раба самому себе.")
        del user_states[user_id]
        return
    if recipient_id == slave_id:
        bot.send_message(message.chat.id, "❌ Нельзя подарить раба ему же самому.")
        del user_states[user_id]
        return
    recipient_data = get_user(recipient_id)
    if not recipient_data or recipient_data.get("blocked"):
        bot.send_message(message.chat.id, "❌ Пользователь не найден или заблокирован.")
        del user_states[user_id]
        return
    user_data = get_user(user_id)
    if slave_id not in user_data.get("slaves", []):
        bot.send_message(message.chat.id, "❌ Вы больше не владеете этим рабом.")
        del user_states[user_id]
        return
    user_data["slaves"].remove(slave_id)
    user_data["sum_slaves"] = len(user_data["slaves"])
    recipient_data["slaves"].append(slave_id)
    recipient_data["sum_slaves"] = len(recipient_data["slaves"])
    update_user(user_id, user_data)
    update_user(recipient_id, recipient_data)

    slave_data = get_user(slave_id)
    donor_name = get_display_name(user_data)
    recipient_name = get_display_name(recipient_data)

    bot.send_message(message.chat.id, f"✅ Вы подарили раба {get_display_name(slave_data)} пользователю {recipient_name}!")
    try:
        bot.send_message(recipient_id, f"🎁 Пользователь {donor_name} подарил вам раба {get_display_name(slave_data)}!")
    except:
        pass
    try:
        bot.send_message(slave_id, f"🎁 Вас подарили игроку {recipient_name} (ID {recipient_id}). Теперь вы его раб.")
    except:
        pass

    del user_states[user_id]
    fake_call = types.CallbackQuery(
        id="fake",
        from_user=message.from_user,
        chat_instance="0",
        message=message,
        data="your_rabs",
        json_string="{}"
    )
    your_rabs_handler(fake_call)

# -------------------- ПОДДЕРЖКА (ТИКЕТЫ) --------------------
@bot.callback_query_handler(func=lambda call: call.data == "support")
def support_menu(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    text = "📞 Опишите вашу проблему. Если нужно, пришлите скриншот (одним сообщением)."
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise
    user_states[call.from_user.id] = {"state": "waiting_support_problem", "msg_id": message_id}

@bot.message_handler(content_types=['text', 'photo'], func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get("state") == "waiting_support_problem")
def process_support_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = user_states[user_id]
    try:
        bot.delete_message(chat_id, state["msg_id"])
    except:
        pass
    problem_text = message.caption if message.caption else message.text
    photo_id = message.photo[-1].file_id if message.photo else None
    if not problem_text:
        problem_text = "Проблема не указана"
    username = message.from_user.username or str(user_id)
    create_ticket(user_id, username, problem_text, photo_id)
    bot.send_message(chat_id, "✅ Ваше обращение отправлено администратору. Ожидайте ответа.")
    del user_states[user_id]

# -------------------- АДМИН ПАНЕЛЬ --------------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    users_count = len(load_users())
    text = (f"🔧 <b>Админ панель</b>\n\n"
            f"📊 Всего пользователей: {users_count}\n\n"
            f"<i>Внимание: при рассылке и ответах на тикеты HTML-разметка НЕ работает (теги не обрабатываются).</i>\n\n"
            f"Выберите действие:")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💰 Пополнить баланс", callback_data="admin_add_balance"),
        InlineKeyboardButton("📢 Рассылка", callback_data="admin_mailing"),
        InlineKeyboardButton("🚫 Заблокировать", callback_data="admin_block"),
        InlineKeyboardButton("🔓 Разблокировать", callback_data="admin_unblock"),
        InlineKeyboardButton("🛡 Выдать щит", callback_data="admin_give_shield"),
        InlineKeyboardButton("💎 Выдать VIP", callback_data="admin_give_vip"),
        InlineKeyboardButton("📋 Список пользователей", callback_data="admin_list_users"),
        InlineKeyboardButton("📨 Открытые тикеты", callback_data="admin_show_tickets"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise

@bot.callback_query_handler(func=lambda call: call.data == "admin_give_shield")
def admin_give_shield_prompt(call):
    msg = bot.send_message(call.message.chat.id, "Введите ID пользователя и количество часов (24/72/168) через пробел.\nПример: 123456 24")
    bot.register_next_step_handler(msg, process_admin_give_shield)

def process_admin_give_shield(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        hours = int(parts[1])
        if hours not in [24, 72, 168]:
            bot.send_message(message.chat.id, "❌ Часы могут быть только 24, 72 или 168.")
            return
        user_data = get_user(user_id)
        if not user_data:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
            return
        now = time.time()
        current = user_data.get("shield_expires", 0)
        if current > now:
            user_data["shield_expires"] = current + hours * 3600
        else:
            user_data["shield_expires"] = now + hours * 3600
        update_user(user_id, user_data)
        bot.send_message(message.chat.id, f"✅ Пользователю {user_id} выдан щит на {hours} часов.")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка ввода. Используйте: ID часы")

@bot.callback_query_handler(func=lambda call: call.data == "admin_give_vip")
def admin_give_vip_prompt(call):
    msg = bot.send_message(call.message.chat.id, "Введите ID пользователя и количество дней VIP (например: 123456 30)")
    bot.register_next_step_handler(msg, process_admin_give_vip)

def process_admin_give_vip(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        days = int(parts[1])
        if days <= 0:
            bot.send_message(message.chat.id, "❌ Количество дней должно быть положительным.")
            return
        user_data = get_user(user_id)
        if not user_data:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
            return
        current = user_data.get("vip_expires", 0)
        if current > time.time():
            user_data["vip_expires"] = current + days * 86400
        else:
            user_data["vip_expires"] = time.time() + days * 86400
        update_user(user_id, user_data)
        bot.send_message(message.chat.id, f"✅ Пользователю {user_id} выдан VIP на {days} дней.")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка ввода. Используйте: ID дни")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_balance")
def admin_add_balance_prompt(call):
    msg = bot.send_message(call.message.chat.id, "Введите ID пользователя и сумму через пробел (например: 123456 100)")
    bot.register_next_step_handler(msg, process_admin_add_balance)

def process_admin_add_balance(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        amount = int(parts[1])
        user_data = get_user(user_id)
        if not user_data:
            bot.send_message(message.chat.id, "Пользователь не найден")
            return
        user_data["balance"] += amount
        update_user(user_id, user_data)
        bot.send_message(message.chat.id, f"✅ Баланс пользователя {user_id} увеличен на {amount} монет.")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка ввода. Используйте: ID сумма")

@bot.callback_query_handler(func=lambda call: call.data == "admin_mailing")
def admin_mailing_prompt(call):
    msg = bot.send_message(call.message.chat.id, "Введите текст рассылки (HTML-теги не работают, будет обычный текст):")
    bot.register_next_step_handler(msg, process_mailing)

def process_mailing(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text
    users = load_users()
    count = 0
    for uid in users:
        try:
            bot.send_message(int(uid), f"📢 Рассылка от администратора:\n{text}")
            count += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(message.chat.id, f"✅ Рассылка отправлена {count} пользователям.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_block")
def admin_block_prompt(call):
    msg = bot.send_message(call.message.chat.id, "Введите ID пользователя для блокировки:")
    bot.register_next_step_handler(msg, process_block)

def process_block(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        uid = int(message.text)
        user_data = get_user(uid)
        if user_data:
            user_data["blocked"] = True
            update_user(uid, user_data)
            bot.send_message(message.chat.id, f"✅ Пользователь {uid} заблокирован.")
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data == "admin_unblock")
def admin_unblock_prompt(call):
    msg = bot.send_message(call.message.chat.id, "Введите ID пользователя для разблокировки:")
    bot.register_next_step_handler(msg, process_unblock)

def process_unblock(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        uid = int(message.text)
        user_data = get_user(uid)
        if user_data:
            user_data["blocked"] = False
            update_user(uid, user_data)
            bot.send_message(message.chat.id, f"✅ Пользователь {uid} разблокирован.")
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "admin_list_users")
def admin_list_users(call):
    users = load_users()
    text = "📋 <b>Список пользователей:</b>\n"
    for uid, data in users.items():
        name = get_display_name(data)
        text += f"ID: {uid} | {name} | Рабов: {data.get('sum_slaves',0)}\n"
        if len(text) > 3000:
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")
            text = ""
    if text:
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_show_tickets")
def admin_show_tickets(call):
    tickets = get_open_tickets()
    if not tickets:
        bot.send_message(call.message.chat.id, "Нет открытых тикетов.")
        return
    text = "📨 <b>Открытые тикеты:</b>\n"
    for tid, data in tickets.items():
        text += f"ID: {tid} | @{data['username']} | {data['problem'][:30]}...\n"
    bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    bot.send_message(call.message.chat.id, "Чтобы ответить, используйте кнопку 'Ответить' под сообщением тикета.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("reply_ticket:"))
def admin_reply_ticket(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    ticket_id = call.data.split(":")[1]
    tickets = load_support_requests()
    if ticket_id not in tickets or tickets[ticket_id]["status"] != "open":
        bot.answer_callback_query(call.id, "Тикет уже закрыт или не существует")
        return
    msg = bot.send_message(call.message.chat.id, f"Введите ответ для пользователя (тикет {ticket_id}):")
    bot.register_next_step_handler(msg, process_admin_reply, ticket_id)

def process_admin_reply(message, ticket_id):
    if message.from_user.id not in ADMIN_IDS:
        return
    tickets = load_support_requests()
    if ticket_id not in tickets:
        bot.send_message(message.chat.id, "Тикет не найден")
        return
    user_id = tickets[ticket_id]["user_id"]
    reply_text = f"🧑‍💻 Ответ администратора:\n{message.text}"
    try:
        bot.send_message(user_id, reply_text)
        tickets[ticket_id]["status"] = "closed"
        save_support_requests(tickets)
        bot.send_message(message.chat.id, "✅ Ответ отправлен пользователю. Тикет закрыт.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Не удалось отправить: {e}")

# -------------------- ЗАПУСК --------------------
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)