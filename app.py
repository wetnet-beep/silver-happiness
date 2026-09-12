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
ADMIN_ID = None

AFK_SHORT_THRESHOLD = 5 * 60
AFK_RECHECK_DELAY = 10 * 60

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
afk_timeout = 2 * 60 * 60
business_conn_id = None

# Мут
muted_users = {}          # {chat_id: {"user_id": ..., "until": ..., "conn_id": ...}}
chat_partners = {}        # {chat_id: user_id} — ID собеседника в каждом чате
mute_text = "🚫 Пользователь замучен"
waiting_mute_text = False

# Флаг ожидания эмодзи возврата
waiting_back_emoji = False

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
            "Команды в бизнес-чатах:\n"
            "`.мут` — замутить навсегда\n"
            "`.мут 10м` — замутить на 10 минут\n"
            "`.мут 1ч` — на 1 час\n"
            "`.анмут` — снять мут\n\n"
            "Команды в боте:\n"
            "/set_mute_text — текст после мута\n"
            "/afk_time 300 — время АФК\n"
            "/set_back_emoji — эмодзи возврата\n"
            "/status — статус",
            parse_mode="Markdown"
        )
        logger.info(f"Админ авторизован: {m.from_user.id}")
    else:
        bot.send_message(m.chat.id, "❌ Неверный пароль. Попробуй ещё раз:")

# ===== ПОЛУЧЕНИЕ ID ЭМОДЗИ =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text 
    and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities),
    content_types=['text']
)
def extract_emoji_id(m):
    global afk_emoji_id, afk_emoji_fallback, back_emoji_id, waiting_back_emoji, last_activity

    if afk_enabled:
        exit_afk()
    last_activity = time.time()

    for entity in m.entities:
        if entity.type == 'custom_emoji':
            emoji_id = entity.custom_emoji_id
            fallback = m.text[entity.offset:entity.offset + entity.length] if entity.offset + entity.length <= len(m.text) else "🌙"

            if waiting_back_emoji:
                back_emoji_id = emoji_id
                waiting_back_emoji = False
                bot.send_message(
                    m.chat.id,
                    f"✅ Эмодзи для возврата сохранён!\nID: `{emoji_id}`",
                    parse_mode="Markdown"
                )
                logger.info(f"Эмодзи возврата сохранён: {emoji_id}")
            else:
                afk_emoji_id = emoji_id
                afk_emoji_fallback = fallback
                bot.send_message(
                    m.chat.id,
                    f"✅ Эмодзи-статус для АФК сохранён!\nID: `{emoji_id}`\nFallback: {fallback}",
                    parse_mode="Markdown"
                )
                logger.info(f"Эмодзи АФК сохранён: {emoji_id}")
            return

# ===== ЭМОДЗИ ВОЗВРАТА =====
@bot.message_handler(commands=['set_back_emoji'])
def set_back_emoji_cmd(m):
    global waiting_back_emoji
    if m.from_user.id != ADMIN_ID:
        return
    waiting_back_emoji = True
    bot.send_message(
        m.chat.id,
        "Отправь Premium-эмодзи, который надо возвращать после АФК.\n"
        "Или напиши `clear`, чтобы статус просто убирался.",
        parse_mode="Markdown"
    )

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text == 'clear' 
    and waiting_back_emoji,
    content_types=['text']
)
def clear_back_emoji(m):
    global back_emoji_id, waiting_back_emoji
    back_emoji_id = None
    waiting_back_emoji = False
    bot.send_message(m.chat.id, "✅ Статус возврата сброшен.")

# ===== ТЕКСТ МУТА =====
@bot.message_handler(commands=['set_mute_text'])
def set_mute_text_cmd(m):
    global waiting_mute_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = True
    bot.send_message(
        m.chat.id,
        f"Текущий текст: {mute_text}\n\n"
        "Отправь новый текст. Можно с Premium-эмодзи.\n"
        "Для отмены: `/cancel`",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['cancel'])
def cancel_cmd(m):
    global waiting_mute_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = False
    bot.send_message(m.chat.id, "Отменено.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and waiting_mute_text and (m.text or m.caption),
    content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice']
)
def receive_mute_text(m):
    global mute_text, waiting_mute_text
    if m.text:
        mute_text = m.text
    elif m.caption:
        mute_text = m.caption
    waiting_mute_text = False
    bot.send_message(m.chat.id, f"✅ Текст мута сохранён:\n{mute_text}")
    logger.info(f"Новый текст мута: {mute_text}")

# ===== АФК ЛОГИКА =====
def enter_afk():
    global afk_enabled, ADMIN_ID, afk_emoji_id, back_emoji_id
    if afk_enabled:
        return
    afk_enabled = True
    logger.info("АФК ВКЛЮЧЁН")

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
                logger.info("Статус убран")
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

# ===== КОМАНДЫ В БОТЕ =====
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
        bot.send_message(m.chat.id, f"✅ Время АФК: {seconds} сек ({h} ч {mnt} мин {s} сек)")
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
        f"• Эмодзи возврата: {back_emoji_id or 'убирается'}\n"
        f"• Текст мута: {mute_text}\n"
        f"• Замучено чатов: {len(muted_users)}"
    )
    bot.send_message(m.chat.id, text)

# ===== МУТ И АНМУТ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and re.match(r'^\.?\s*мут\b', m.text, re.IGNORECASE)
)
def handle_mute(m):
    global mute_text
    cid = m.chat.id
    conn_id = m.business_connection_id
    text = m.text.strip()

    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except Exception as e:
        logger.error(f"Ошибка удаления команды: {e}")

    # Парсим время
    parts = text.split(maxsplit=1)
    duration = None
    if len(parts) > 1:
        time_str = parts[1].strip().lower()
        match = re.match(r'^(\d+)\s*([сcмmчhдd]?)$', time_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            multipliers = {'с': 1, 'c': 1, 'м': 60, 'm': 60, 'ч': 3600, 'h': 3600, 'д': 86400, 'd': 86400}
            duration = value * multipliers.get(unit, 1)

    # Цель
    target_id = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target_id = m.reply_to_message.from_user.id
    elif m.from_user.id != ADMIN_ID:
        target_id = m.from_user.id
    else:
        target_id = chat_partners.get(cid)

    if not target_id:
        try:
            bot.send_message(cid, "❌ Не знаю, кого мутить. Ответь на сообщение или дождись, пока собеседник напишет.", business_connection_id=conn_id)
        except:
            pass
        return

    until = time.time() + duration if duration else None
    muted_users[cid] = {"user_id": target_id, "until": until, "conn_id": conn_id}
    logger.info(f"Замучен {target_id} в чате {cid}, до {until}")

    try:
        bot.send_message(cid, mute_text, business_connection_id=conn_id)
    except Exception as e:
        logger.error(f"Ошибка отправки текста мута: {e}")

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and re.match(r'^\.?\s*анмут\b', m.text, re.IGNORECASE)
)
def handle_unmute(m):
    cid = m.chat.id
    conn_id = m.business_connection_id

    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    if cid in muted_users:
        del muted_users[cid]
        logger.info(f"Мут снят в чате {cid}")
        try:
            bot.send_message(cid, "🔓 Мут снят", business_connection_id=conn_id)
        except:
            pass
    else:
        try:
            bot.send_message(cid, "❌ Нет активного мута", business_connection_id=conn_id)
        except:
            pass

# ===== ОТСЛЕЖИВАНИЕ АКТИВНОСТИ =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID,
    content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice']
)
def track_activity(m):
    global last_activity, afk_enabled
    last_activity = time.time()
    if afk_enabled:
        logger.info("Активность админа — выхожу из АФК")
        exit_afk()

# ===== BUSINESS =====
@bot.business_message_handler(func=lambda m: True)
def handle_business(m):
    global business_conn_id, muted_users, chat_partners

    business_conn_id = m.business_connection_id
    cid = m.chat.id
    uid = m.from_user.id

    # Запоминаем собеседника
    if ADMIN_ID and uid != ADMIN_ID:
        if cid not in chat_partners:
            chat_partners[cid] = uid
            logger.info(f"Запомнен собеседник {cid}: {uid}")

    # Проверка мута
    if cid in muted_users:
        mute_info = muted_users[cid]
        if mute_info["until"] and time.time() > mute_info["until"]:
            del muted_users[cid]
            logger.info(f"Мут истёк в {cid}")
        elif mute_info["user_id"] == uid:
            try:
                bot.delete_business_messages(m.business_connection_id, [m.message_id])
                logger.info(f"Удалено сообщение замученного {uid}")
            except Exception as e:
                logger.error(f"Ошибка удаления: {e}")
            return

    # Активность админа
    if ADMIN_ID and uid == ADMIN_ID:
        track_activity(m)

# ===== FLASK =====
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
