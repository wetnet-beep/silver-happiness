import telebot
import time
import threading
import logging
import os
import re
from telebot import types

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")
PASSWORD = "qwer1"
ADMIN_ID = None  # Заполнится после авторизации

# АФК настройки
AFK_TIMEOUT = 2 * 60 * 60      # 2 часа
AFK_SHORT_THRESHOLD = 5 * 60   # 5 минут
AFK_RECHECK_DELAY = 10 * 60    # 10 минут

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN, threaded=False)

# ===== СОСТОЯНИЕ =====
user_state = {}          # {user_id: 'awaiting_password' | 'authorized'}
afk_enabled = False
last_activity = time.time()
afk_emoji_id = None      # ID эмодзи-статуса (заполняется из сообщения)
afk_emoji_fallback = "🌙"
base_name = "Твоё Имя"   # Твоё настоящее имя (для Business, если понадобится)
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
            "Отправь боту Premium-эмодзи для АФК-статуса.\n"
            "Бот запомнит его ID.\n\n"
            "Команды:\n"
            "/afk_on — включить АФК вручную\n"
            "/afk_off — выключить АФК\n"
            "/status — статус"
        )
        logger.info(f"Админ авторизован: {m.from_user.id}")
    else:
        bot.send_message(m.chat.id, "❌ Неверный пароль. Попробуй ещё раз:")

# ===== ПОЛУЧЕНИЕ ID ЭМОДЗИ =====
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text and m.entities, content_types=['text'])
def extract_emoji_id(m):
    """Вытаскивает custom_emoji_id из сообщения с Premium-эмодзи"""
    global afk_emoji_id, afk_emoji_fallback
    
    for entity in m.entities:
        if entity.type == 'custom_emoji':
            afk_emoji_id = entity.custom_emoji_id
            # Пытаемся получить fallback (обычный эмодзи)
            if entity.offset + entity.length <= len(m.text):
                afk_emoji_fallback = m.text[entity.offset:entity.offset + entity.length]
            
            bot.send_message(
                m.chat.id,
                f"✅ Эмодзи-статус сохранён!\n"
                f"ID: `{afk_emoji_id}`\n"
                f"Fallback: {afk_emoji_fallback}",
                parse_mode="Markdown"
            )
            logger.info(f"Эмодзи-статус сохранён: {afk_emoji_id}")
            return
    
    bot.send_message(m.chat.id, "❌ Это не Premium-эмодзи. Отправь кастомный.")

# ===== АФК ЛОГИКА =====
def enter_afk():
    global afk_enabled, ADMIN_ID, afk_emoji_id
    
    if afk_enabled:
        return
    afk_enabled = True
    logger.info("АФК ВКЛЮЧЁН")
    
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
        bot.send_message(ADMIN_ID, f"🌙 АФК включён (молчал 2 часа)")

def exit_afk():
    global afk_enabled, ADMIN_ID
    
    if not afk_enabled:
        return
    afk_enabled = False
    logger.info("АФК ВЫКЛЮЧЁН")
    
    if ADMIN_ID:
        try:
            bot.set_user_emoji_status(
                user_id=ADMIN_ID,
                emoji_status_custom_emoji_id=""
            )
            logger.info("Статус снят")
        except Exception as e:
            logger.error(f"Ошибка снятия статуса: {e}")
        
        bot.send_message(ADMIN_ID, "☀️ АФК выключен")

def afk_watcher():
    """Проверяет неактивность (2 часа)"""
    global afk_enabled, last_activity
    while True:
        time.sleep(30)
        if afk_enabled:
            continue
        if time.time() - last_activity >= AFK_TIMEOUT:
            enter_afk()

def afk_recheck_watcher():
    """Если после выхода писал меньше 5 мин — вернуть АФК через 10 мин"""
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
        f"• Эмодзи ID: {afk_emoji_id or 'не задан'}"
    )
    bot.send_message(m.chat.id, text)

# ===== ОТСЛЕЖИВАНИЕ АКТИВНОСТИ =====
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID, content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice'])
def track_activity(m):
    global last_activity
    last_activity = time.time()
    if afk_enabled:
        exit_afk()

# ===== BUSINESS (если нужно) =====
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
    # Фоновые потоки
    threading.Thread(target=afk_watcher, daemon=True).start()
    threading.Thread(target=afk_recheck_watcher, daemon=True).start()
    
    # Бот в фоне
    threading.Thread(target=lambda: bot.polling(none_stop=True, interval=1), daemon=True).start()
    
    # Flask на порту Render
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
