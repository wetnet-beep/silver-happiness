import telebot
import time
import threading
import logging
import os
from telebot import types

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")
PASSWORD = "qwer1"
ADMIN_ID = None

AFK_SHORT_THRESHOLD = 5 * 60   # 5 минут
AFK_RECHECK_DELAY = 10 * 60    # 10 минут

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN, threaded=False)

# ===== СОСТОЯНИЕ =====
user_state = {}
afk_enabled = False
last_activity = time.time()
afk_emoji_id = None
afk_emoji_fallback = "🌙"
back_emoji_id = None
afk_timeout = 2 * 60 * 60  # по умолчанию 2 часа

business_conn_id = None

# ===== АВТОРИЗАЦИЯ =====
@bot.message_handler(commands=['start'])
def start_cmd(m):
    uid = m.from_user.id
    if user_state.get(uid) == 'authorized':
        bot.send_message(uid, "Ты уже авторизован. Бот работает.")
        return
    user_state[uid] = 'awaiting_password'
    bot.send_message(uid, "Введите пароль:")

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == 'awaiting_password')
def check_password(m):
    global ADMIN_ID
    if m.text == PASSWORD:
        user_state[m.from_user.id] = 'authorized'
        ADMIN_ID = m.from_user.id
        bot.send_message(
            m.chat.id,
            "✅ Пароль принят. Ты админ.\n\n"
            "Отправь боту Premium-эмодзи для АФК-статуса.\n\n"
            "Команды:\n"
            "/afk_on — включить АФК вручную\n"
            "/afk_off — выключить АФК\n"
            "/afk_time 300 — время АФК (30–86400 сек)\n"
            "/set_back_emoji — задать эмодзи для возврата\n"
            "/status — статус"
        )
        logger.info(f"Админ авторизован: {m.from_user.id}")
    else:
        bot.send_message(m.chat.id, "❌ Неверный пароль. Попробуй ещё раз:")

# ===== ПОЛУЧЕНИЕ ID ЭМОДЗИ АФК =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text 
    and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities),
    content_types=['text']
)
def extract_emoji_id(m):
    global afk_emoji_id, afk_emoji_fallback
    for entity in m.entities:
        if entity.type == 'custom_emoji':
            afk_emoji_id = entity.custom_emoji_id
            if entity.offset + entity.length <= len(m.text):
                afk_emoji_fallback = m.text[entity.offset:entity.offset + entity.length]
            bot.send_message(
                m.chat.id,
                f"✅ Эмодзи-статус сохранён!\nID: `{afk_emoji_id}`\nFallback: {afk_emoji_fallback}",
                parse_mode="Markdown"
            )
            logger.info(f"Эмодзи-статус сохранён: {afk_emoji_id}")
            return

# ===== РУЧНОЕ ЗАДАНИЕ ЭМОДЗИ ДЛЯ ВОЗВРАТА =====
@bot.message_handler(commands=['set_back_emoji'])
def set_back_emoji_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    bot.send_message(
        m.chat.id,
        "Отправь Premium-эмодзи, который надо возвращать после АФК.\n"
        "Или напиши `clear`, чтобы статус просто убирался.",
        parse_mode="Markdown"
    )

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text == 'clear',
    content_types=['text']
)
def clear_back_emoji(m):
    global back_emoji_id
    back_emoji_id = None
    bot.send_message(m.chat.id, "✅ Статус возврата сброшен. После АФК статус будет убираться.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text 
    and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities),
    content_types=['text']
)
def extract_back_emoji_id(m):
    global back_emoji_id
    for entity in m.entities:
        if entity.type == 'custom_emoji':
            back_emoji_id = entity.custom_emoji_id
            bot.send_message(
                m.chat.id,
                f"✅ Эмодзи для возврата сохранён!\nID: `{back_emoji_id}`",
                parse_mode="Markdown"
            )
            logger.info(f"Эмодзи возврата сохранён: {back_emoji_id}")
            return

# ===== АФК ЛОГИКА =====
def enter_afk():
    global afk_enabled, ADMIN_ID, afk_emoji_id, back_emoji_id
    if afk_enabled:
        return
    afk_enabled = True
    logger.info("АФК ВКЛЮЧЁН")

    # Пробуем запомнить текущий статус (может не сработать)
    if ADMIN_ID and back_emoji_id is None:
        try:
            chat_info = bot.get_chat(ADMIN_ID)
            if hasattr(chat_info, 'emoji_status_custom_emoji_id') and chat_info.emoji_status_custom_emoji_id:
                back_emoji_id = chat_info.emoji_status_custom_emoji_id
                logger.info(f"Запомнен старый статус: {back_emoji_id}")
        except Exception as e:
            logger.warning(f"Не удалось прочитать старый статус: {e}")

    if afk_emoji_id and ADMIN_ID:
        try:
            bot.set_user_emoji_status(
                user_id=ADMIN_ID,
                emoji_status_custom_emoji_id=afk_emoji_id
            )
            logger.info(f"Статус установлен: {afk_emoji_id}")
        except Exception as e:
            logger.error(f"Ошибка смены статуса: {e}")

    if ADMIN_ID:
        bot.send_message(ADMIN_ID, "🌙 АФК включён")

def exit_afk():
    global afk_enabled, ADMIN_ID, back_emoji_id
    if not afk_enabled:
        return
    afk_enabled = False
    logger.info("АФК ВЫКЛЮЧЁН")

    if ADMIN_ID:
        try:
            if back_emoji_id:
                bot.set_user_emoji_status(
                    user_id=ADMIN_ID,
                    emoji_status_custom_emoji_id=back_emoji_id
                )
                logger.info(f"Статус возвращён: {back_emoji_id}")
            else:
                bot.set_user_emoji_status(
                    user_id=ADMIN_ID,
                    emoji_status_custom_emoji_id=""
                )
                logger.info("Статус убран (старый неизвестен)")
        except Exception as e:
            logger.error(f"Ошибка смены статуса: {e}")

        bot.send_message(ADMIN_ID, "☀️ АФК выключен")

def afk_watcher():
    global afk_enabled, last_activity, afk_timeout
    while True:
        time.sleep(30)
        if afk_enabled:
            continue
        if time.time() - last_activity >= afk_timeout:
            enter_afk()

def afk_recheck_watcher():
    global afk_enabled, last_activity
    while True:
        time.sleep(60)
        if not afk_enabled:
            continue
        idle_since_exit = time.time() - last_activity
        if idle_since_exit >= AFK_RECHECK_DELAY:
            enter_afk()

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['afk_on'])
def manual_afk_on(m):
    if m.from_user.id != ADMIN_ID:
        return
    enter_afk()
    bot.send_message(m.chat.id, "АФК включён вручную.")

@bot.message_handler(commands=['afk_off'])
def manual_afk_off(m):
    if m.from_user.id != ADMIN_ID:
        return
    exit_afk()
    global last_activity
    last_activity = time.time()
    bot.send_message(m.chat.id, "АФК выключен вручную.")

@bot.message_handler(commands=['afk_time'])
def set_afk_time(m):
    global afk_timeout
    if m.from_user.id != ADMIN_ID:
        return

    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        h = afk_timeout // 3600
        mnt = (afk_timeout % 3600) // 60
        s = afk_timeout % 60
        bot.send_message(
            m.chat.id,
            f"⏱ Текущее время АФК: {afk_timeout} сек ({h} ч {mnt} мин {s} сек)\n\n"
            "Использование: `/afk_time 300`\n"
            "От 30 до 86400 секунд (24 часа).",
            parse_mode="Markdown"
        )
        return

    try:
        seconds = int(parts[1])
        if seconds < 30 or seconds > 86400:
            bot.send_message(m.chat.id, "❌ Время должно быть от 30 до 86400 секунд.")
            return
        afk_timeout = seconds
        h = seconds // 3600
        mnt = (seconds % 3600) // 60
        s = seconds % 60
        bot.send_message(m.chat.id, f"✅ Время АФК установлено: {seconds} сек ({h} ч {mnt} мин {s} сек)")
        logger.info(f"Новое время АФК: {seconds} сек")
    except ValueError:
        bot.send_message(m.chat.id, "❌ Отправь число. Например: `/afk_time 300`", parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    idle = int(time.time() - last_activity)
    mins = idle // 60
    text = (
        f"📊 Статус:\n"
        f"• АФК: {'ВКЛ' if afk_enabled else 'ВЫКЛ'}\n"
        f"• Молчание: {mins} мин\n"
        f"• Время АФК: {afk_timeout} сек\n"
        f"• Эмодзи АФК: {afk_emoji_id or 'не задан'}\n"
        f"• Эмодзи возврата: {back_emoji_id or 'убирается'}"
    )
    bot.send_message(m.chat.id, text)

# ===== ОТСЛЕЖИВАНИЕ АКТИВНОСТИ =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID,
    content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice']
)
def track_activity(m):
    global last_activity
    last_activity = time.time()
    if afk_enabled:
        exit_afk()

# ===== BUSINESS =====
@bot.business_message_handler(func=lambda m: True)
def handle_business(m):
    global business_conn_id
    business_conn_id = m.business_connection_id
    if ADMIN_ID and m.from_user.id == ADMIN_ID:
        track_activity(m)

# ===== FLASK ДЛЯ RENDER =====
from flask import Flask
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "OK"

# ===== ЗАПУСК =====
if __name__ == "__main__":
    threading.Thread(target=afk_watcher, daemon=True).start()
    threading.Thread(target=afk_recheck_watcher, daemon=True).start()

    def run_bot():
        logger.info("Запуск бота...")
        try:
            bot.polling(none_stop=True, interval=1)
        except Exception as e:
            logger.error(f"Бот упал: {e}")

    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
