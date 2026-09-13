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

muted_users = {}
chat_partners = {}
mute_text = "🚫 Пользователь замучен"
mute_entities = None
waiting_mute_text = False
waiting_back_emoji = False

warn_text = "⚠️ Варник) {count}/{limit}"
warn_entities = None
warn_limit = 3
waiting_warn_text = False
warned_users = {}

bypass_enabled = {}

# ===== МЕНЮ =====
def send_commands(chat_id):
    bot.send_message(
        chat_id,
        "<b>📋 Список команд:</b>\n\n"
        "<b>⚙️ Настройки (в личке с ботом):</b>\n"
        "/start — показать это меню\n"
        "/status — статус бота\n"
        "/afk_on — включить АФК вручную\n"
        "/afk_off — выключить АФК вручную\n"
        "/afk_time 300 — время до АФК (30–86400 сек)\n"
        "/set_mute_text — задать текст после мута\n"
        "/set_warn_text — задать текст варна\n"
        "/set_warn_limit 3 — лимит варнов\n"
        "/set_back_emoji — эмодзи возврата после АФК\n"
        "/cancel — отменить ввод\n\n"
        "<b>🎬 В бизнес-чатах (отдельным сообщением):</b>\n"
        "<code>мут</code> — замутить навсегда\n"
        "<code>мут 10м</code> — на 10 минут\n"
        "<code>анмут</code> — снять мут\n"
        "<code>варн</code> — активировать варны\n"
        "<code>обход</code> — вкл/выкл дублирование\n\n"
        "<b>💡 Premium-эмодзи для АФК:</b> просто отправь боту.",
        parse_mode="HTML"
    )

# ===== АВТОРИЗАЦИЯ =====
@bot.message_handler(commands=['start'])
def start_cmd(m):
    uid = m.from_user.id
    if user_state.get(uid) == 'authorized':
        send_commands(uid)
        return
    user_state[uid] = 'awaiting_password'
    bot.send_message(uid, "Введите пароль:")

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == 'awaiting_password')
def check_password(m):
    global ADMIN_ID
    if m.text == PASSWORD:
        user_state[m.from_user.id] = 'authorized'
        ADMIN_ID = m.from_user.id
        bot.send_message(m.chat.id, "✅ Пароль принят. Ты админ.")
        send_commands(m.chat.id)
        logger.info(f"Админ авторизован: {m.from_user.id}")
    else:
        bot.send_message(m.chat.id, "❌ Неверный пароль. Попробуй ещё раз:")

# ===== ЭМОДЗИ АФК =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text 
    and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities)
    and not waiting_mute_text
    and not waiting_back_emoji
    and not waiting_warn_text,
    content_types=['text']
)
def extract_emoji_id(m):
    global afk_emoji_id, afk_emoji_fallback, last_activity

    if afk_enabled:
        exit_afk()
    last_activity = time.time()

    for entity in m.entities:
        if entity.type == 'custom_emoji':
            afk_emoji_id = entity.custom_emoji_id
            afk_emoji_fallback = m.text[entity.offset:entity.offset + entity.length] if entity.offset + entity.length <= len(m.text) else "🌙"
            bot.send_message(
                m.chat.id,
                f"✅ Эмодзи-статус для АФК сохранён!\nID: `{afk_emoji_id}`",
                parse_mode="Markdown"
            )
            logger.info(f"Эмодзи АФК сохранён: {afk_emoji_id}")
            return

# ===== ЭМОДЗИ ВОЗВРАТА =====
@bot.message_handler(commands=['set_back_emoji'])
def set_back_emoji_cmd(m):
    global waiting_back_emoji
    if m.from_user.id != ADMIN_ID:
        return
    waiting_back_emoji = True
    bot.send_message(m.chat.id, "Отправь Premium-эмодзи для возврата после АФК. Или <code>clear</code>, чтобы убирать.", parse_mode="HTML")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and m.text == 'clear' and waiting_back_emoji,
    content_types=['text']
)
def clear_back_emoji(m):
    global back_emoji_id, waiting_back_emoji
    back_emoji_id = None
    waiting_back_emoji = False
    bot.send_message(m.chat.id, "✅ Статус возврата сброшен.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text 
    and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities)
    and waiting_back_emoji,
    content_types=['text']
)
def extract_back_emoji_id(m):
    global back_emoji_id, waiting_back_emoji
    for entity in m.entities:
        if entity.type == 'custom_emoji':
            back_emoji_id = entity.custom_emoji_id
            waiting_back_emoji = False
            bot.send_message(m.chat.id, f"✅ Эмодзи возврата: `{back_emoji_id}`", parse_mode="Markdown")
            logger.info(f"Эмодзи возврата: {back_emoji_id}")
            return

# ===== ТЕКСТ МУТА =====
@bot.message_handler(commands=['set_mute_text'])
def set_mute_text_cmd(m):
    global waiting_mute_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = True
    bot.send_message(m.chat.id, f"Текущий текст: {mute_text}\n\nОтправь новый (можно с Premium-эмодзи).\nДля отмены: /cancel")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and waiting_mute_text and (m.text or m.caption),
    content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice']
)
def receive_mute_text(m):
    global mute_text, mute_entities, waiting_mute_text
    if m.text:
        mute_text = m.text
        mute_entities = m.entities
    elif m.caption:
        mute_text = m.caption
        mute_entities = m.caption_entities
    waiting_mute_text = False
    bot.send_message(m.chat.id, f"✅ Текст мута сохранён:\n{mute_text}")
    logger.info(f"Новый текст мута: {mute_text}")

# ===== ТЕКСТ ВАРНА =====
@bot.message_handler(commands=['set_warn_text'])
def set_warn_text_cmd(m):
    global waiting_warn_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_warn_text = True
    bot.send_message(
        m.chat.id,
        f"Текущий текст варна: {warn_text}\n\n"
        "Отправь новый текст (можно с Premium-эмодзи).\n"
        "Используй <code>{count}</code> для номера и <code>{limit}</code> для лимита.\n"
        "Пример: <code>⚠️ Варник) {count}/{limit}</code>\n\n"
        "Для отмены: /cancel",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['set_warn_limit'])
def set_warn_limit_cmd(m):
    global warn_limit
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(m.chat.id, f"Текущий лимит: {warn_limit}\n\nИспользование: /set_warn_limit 3")
        return
    try:
        limit = int(parts[1])
        if limit < 1 or limit > 100:
            bot.send_message(m.chat.id, "❌ Лимит от 1 до 100.")
            return
        warn_limit = limit
        bot.send_message(m.chat.id, f"✅ Лимит варнов: {warn_limit}")
    except ValueError:
        bot.send_message(m.chat.id, "❌ Отправь число.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and waiting_warn_text and (m.text or m.caption),
    content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice']
)
def receive_warn_text(m):
    global warn_text, warn_entities, waiting_warn_text
    if m.text:
        warn_text = m.text
        warn_entities = m.entities
    elif m.caption:
        warn_text = m.caption
        warn_entities = m.caption_entities
    waiting_warn_text = False
    bot.send_message(m.chat.id, f"✅ Текст варна сохранён:\n{warn_text}")
    logger.info(f"Новый текст варна: {warn_text}")

@bot.message_handler(commands=['cancel'])
def cancel_cmd(m):
    global waiting_mute_text, waiting_back_emoji, waiting_warn_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = False
    waiting_back_emoji = False
    waiting_warn_text = False
    bot.send_message(m.chat.id, "Отменено.")

# ===== АФК =====
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
        except Exception as e:
            logger.warning(f"Не удалось прочитать старый статус: {e}")

    if afk_emoji_id and ADMIN_ID:
        try:
            bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id=afk_emoji_id)
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
                bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id=back_emoji_id)
            else:
                bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id="")
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
        if time.time() - last_activity >= AFK_RECHECK_DELAY:
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
        bot.send_message(m.chat.id, f"Текущее время: {afk_timeout} сек\nИспользование: /afk_time 300")
        return
    try:
        seconds = int(parts[1])
        if seconds < 30 or seconds > 86400:
            bot.send_message(m.chat.id, "❌ От 30 до 86400 сек.")
            return
        afk_timeout = seconds
        bot.send_message(m.chat.id, f"✅ Время АФК: {seconds} сек")
    except ValueError:
        bot.send_message(m.chat.id, "❌ Отправь число.")

@bot.message_handler(commands=['status'])
def status_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    idle = int(time.time() - last_activity)
    text = (
        f"📊 Статус:\n"
        f"• АФК: {'ВКЛ' if afk_enabled else 'ВЫКЛ'}\n"
        f"• Молчание: {idle // 60} мин\n"
        f"• Время АФК: {afk_timeout} сек\n"
        f"• Эмодзи АФК: {afk_emoji_id or 'не задан'}\n"
        f"• Эмодзи возврата: {back_emoji_id or 'убирается'}\n"
        f"• Текст мута: {mute_text}\n"
        f"• Текст варна: {warn_text}\n"
        f"• Лимит варнов: {warn_limit}\n"
        f"• Замучено чатов: {len(muted_users)}"
    )
    bot.send_message(m.chat.id, text)

# ===== ХЕЛПЕР: ПРОВЕРКА ЧТО ЭТО КОМАНДА =====
def is_command(text, cmd):
    """Проверяет, что текст начинается с команды как отдельного слова"""
    if not text:
        return False
    # Убираем лишние пробелы
    stripped = text.strip()
    # Команда должна быть первым словом
    parts = stripped.split(maxsplit=1)
    if not parts:
        return False
    return parts[0].lower() == cmd.lower()

# ===== МУТ / АНМУТ / ВАРН / ОБХОД =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "мут")
)
def handle_mute(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    text = m.text.strip()

    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")

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

    target_id = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target_id = m.reply_to_message.from_user.id
    elif m.from_user.id != ADMIN_ID:
        target_id = m.from_user.id
    else:
        target_id = chat_partners.get(cid)

    if not target_id:
        try:
            bot.send_message(cid, "❌ Не знаю, кого мутить.", business_connection_id=conn_id)
        except:
            pass
        return

    until = time.time() + duration if duration else None
    muted_users[cid] = {"user_id": target_id, "until": until, "conn_id": conn_id}
    logger.info(f"Замучен {target_id} в {cid}")

    try:
        bot.send_message(cid, mute_text, entities=mute_entities, business_connection_id=conn_id)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        try:
            bot.send_message(cid, mute_text, business_connection_id=conn_id)
        except:
            pass

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "анмут")
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
        try:
            bot.send_message(cid, "🔓 Мут снят", business_connection_id=conn_id)
        except:
            pass
    else:
        try:
            bot.send_message(cid, "❌ Нет активного мута", business_connection_id=conn_id)
        except:
            pass

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "варн")
)
def handle_warn(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    target_id = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target_id = m.reply_to_message.from_user.id
    else:
        target_id = chat_partners.get(cid)

    if not target_id:
        try:
            bot.send_message(cid, "❌ Не знаю, кому варн.", business_connection_id=conn_id)
        except:
            pass
        return

    warned_users[cid] = {"user_id": target_id, "count": 0}
    try:
        bot.send_message(cid, f"⚠️ Варн активирован. Лимит: {warn_limit}", business_connection_id=conn_id)
    except:
        pass

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "обход")
)
def handle_bypass(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    if bypass_enabled.get(cid):
        bypass_enabled[cid] = False
        try:
            bot.send_message(cid, "🛑 Обход выключен", business_connection_id=conn_id)
        except:
            pass
    else:
        bypass_enabled[cid] = True
        try:
            bot.send_message(cid, "🔄 Обход включён", business_connection_id=conn_id)
        except:
            pass

# ===== АКТИВНОСТЬ =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID,
    content_types=['text', 'photo', 'video', 'sticker', 'document', 'voice']
)
def track_activity(m):
    global last_activity, afk_enabled
    last_activity = time.time()
    if afk_enabled:
        exit_afk()

# ===== BUSINESS =====
@bot.business_message_handler(func=lambda m: True)
def handle_business(m):
    global business_conn_id, muted_users, chat_partners, warned_users

    business_conn_id = m.business_connection_id
    cid = m.chat.id
    uid = m.from_user.id

    if ADMIN_ID and uid != ADMIN_ID:
        if cid not in chat_partners:
            chat_partners[cid] = uid

    # Мут
    if cid in muted_users:
        mute_info = muted_users[cid]
        if mute_info["until"] and time.time() > mute_info["until"]:
            del muted_users[cid]
        elif mute_info["user_id"] == uid:
            try:
                bot.delete_business_messages(m.business_connection_id, [m.message_id])
            except:
                pass
            return

    # Варны
    if cid in warned_users:
        warn_info = warned_users[cid]
        if warn_info["user_id"] == uid and uid != ADMIN_ID:
            warn_info["count"] += 1
            logger.info(f"Варн {warn_info['count']}/{warn_limit} для {uid}")

            if warn_info["count"] >= warn_limit:
                muted_users[cid] = {"user_id": uid, "until": None, "conn_id": m.business_connection_id}
                del warned_users[cid]
                try:
                    bot.send_message(cid, "🚫 Лимит варнов достигнут. Мут навсегда.", business_connection_id=m.business_connection_id)
                except:
                    pass
            else:
                text = warn_text.replace("{count}", str(warn_info["count"])).replace("{limit}", str(warn_limit))
                try:
                    bot.send_message(cid, text, entities=warn_entities, business_connection_id=m.business_connection_id)
                except Exception as e:
                    logger.error(f"Ошибка варна: {e}")
                    try:
                        bot.send_message(cid, text, business_connection_id=m.business_connection_id)
                    except:
                        pass

    # Обход
    if ADMIN_ID and uid == ADMIN_ID and bypass_enabled.get(cid):
        try:
            bot.delete_business_messages(m.business_connection_id, [m.message_id])
        except:
            pass
        try:
            if m.text:
                bot.send_message(cid, m.text, entities=m.entities, business_connection_id=m.business_connection_id)
            elif m.photo:
                bot.send_photo(cid, m.photo[-1].file_id, caption=m.caption, business_connection_id=m.business_connection_id)
            elif m.video:
                bot.send_video(cid, m.video.file_id, caption=m.caption, business_connection_id=m.business_connection_id)
            elif m.sticker:
                bot.send_sticker(cid, m.sticker.file_id, business_connection_id=m.business_connection_id)
            elif m.document:
                bot.send_document(cid, m.document.file_id, business_connection_id=m.business_connection_id)
            elif m.voice:
                bot.send_voice(cid, m.voice.file_id, business_connection_id=m.business_connection_id)
        except Exception as e:
            logger.error(f"Ошибка обхода: {e}")
        return

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
