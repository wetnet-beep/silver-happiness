import telebot
import time
import threading
import logging
import os
import re
import random
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
chat_partners = {}  # {chat_id: {"id": ..., "name": ...}}
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
echo_enabled = {}

rps_games = {}
rek_games = {}

waiting_save = False

UNMUTE_EMOJI_ID = "5386436816557601037"
BYPASS_EMOJI_ID = "5841243255856960314"
HELLO_EMOJI_ID = "5386436816557601037"

# ===== СПИСОК КОМАНД =====
COMMANDS_LIST = """<b>📋 Список команд</b>

<b>⚙️ Настройки (в личке):</b>
<code>/start</code> — приветствие
<code>/status</code> — статус бота
<code>/afk_on</code> — вкл АФК
<code>/afk_off</code> — выкл АФК
<code>/afk_time 300</code> — время АФК (30–86400 сек)
<code>/set_mute_text</code> — текст после мута
<code>/set_warn_text</code> — текст варна
<code>/set_warn_limit 3</code> — лимит варнов
<code>/set_back_emoji</code> — эмодзи возврата
<code>сейф</code> — сохранить медиа
<code>/cancel</code> — отменить ввод

<b>🎬 В бизнес-чатах:</b>
<code>мут</code> — замутить навсегда
<code>мут 10м</code> — замутить на 10 минут
<code>анмут</code> — снять мут
<code>варн</code> — активировать варны
<code>обход</code> — вкл/выкл дублирование
<code>эхо</code> — повторять за собеседником
<code>сейф</code> — ответом на медиа → в ЛС
<code>спам слово 5</code> — спам (по умолч. 15, макс 30)
<code>аним текст</code> — печатает по буквам
<code>шар вопрос</code> — магический шар
<code>рек</code> — игра на реакцию
<code>рпс</code> — камень-ножницы-бумага
<code>монетка</code> — подбросить монетку

<b>💡 Premium-эмодзи для АФК:</b> просто отправь боту."""

# ===== ПРИВЕТСТВИЕ =====
def send_hello(chat_id):
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton(
        text="📋 Список команд",
        callback_data="show_commands",
        style="primary"
    )
    markup.add(btn)

    text = f'привет хозяин!<tg-emoji emoji-id="{HELLO_EMOJI_ID}">👋</tg-emoji>'

    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка приветствия: {e}")
        bot.send_message(chat_id, "привет хозяин!", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_commands")
def callback_show_commands(call):
    try:
        bot.send_message(call.message.chat.id, COMMANDS_LIST, parse_mode="HTML")
        bot.answer_callback_query(call.id, "📋 Отправлено")
    except Exception as e:
        logger.error(f"Ошибка команд: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# ===== АВТОРИЗАЦИЯ =====
@bot.message_handler(commands=['start'])
def start_cmd(m):
    uid = m.from_user.id
    if user_state.get(uid) == 'authorized':
        send_hello(uid)
        return
    user_state[uid] = 'awaiting_password'
    bot.send_message(uid, "Введите пароль:")

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == 'awaiting_password')
def check_password(m):
    global ADMIN_ID
    if m.text == PASSWORD:
        user_state[m.from_user.id] = 'authorized'
        ADMIN_ID = m.from_user.id
        bot.send_message(m.chat.id, "✅ Пароль принят.")
        send_hello(m.chat.id)
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
            return

# ===== ЭМОДЗИ ВОЗВРАТА =====
@bot.message_handler(commands=['set_back_emoji'])
def set_back_emoji_cmd(m):
    global waiting_back_emoji
    if m.from_user.id != ADMIN_ID:
        return
    waiting_back_emoji = True
    bot.send_message(m.chat.id, "Отправь Premium-эмодзи для возврата. Или <code>clear</code>.", parse_mode="HTML")

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
            return

# ===== ТЕКСТ МУТА =====
@bot.message_handler(commands=['set_mute_text'])
def set_mute_text_cmd(m):
    global waiting_mute_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = True
    bot.send_message(m.chat.id, f"Текущий текст: {mute_text}\n\nОтправь новый. /cancel — отмена.")

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

# ===== ТЕКСТ ВАРНА =====
@bot.message_handler(commands=['set_warn_text'])
def set_warn_text_cmd(m):
    global waiting_warn_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_warn_text = True
    bot.send_message(
        m.chat.id,
        f"Текущий текст: {warn_text}\n\n"
        "Используй <code>{count}</code> и <code>{limit}</code>.",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['set_warn_limit'])
def set_warn_limit_cmd(m):
    global warn_limit
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(m.chat.id, f"Текущий лимит: {warn_limit}\n/set_warn_limit 3")
        return
    try:
        limit = int(parts[1])
        if limit < 1 or limit > 100:
            bot.send_message(m.chat.id, "❌ От 1 до 100.")
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

@bot.message_handler(commands=['cancel'])
def cancel_cmd(m):
    global waiting_mute_text, waiting_back_emoji, waiting_warn_text, waiting_save
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = False
    waiting_back_emoji = False
    waiting_warn_text = False
    waiting_save = False
    bot.send_message(m.chat.id, "Отменено.")

# ===== СЕЙФ (ЛИЧКА) =====
def send_error_to_admin(text):
    if ADMIN_ID:
        try:
            bot.send_message(ADMIN_ID, f"⚠️ Ошибка:\n{text}")
        except:
            pass

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and m.text and m.text.strip().lower() == "сейф"
)
def save_cmd(m):
    global waiting_save
    waiting_save = True
    bot.send_message(m.chat.id, "Отправь медиа — сохраню.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and waiting_save,
    content_types=['photo', 'video', 'document', 'voice', 'sticker', 'audio', 'video_note']
)
def save_media(m):
    global waiting_save
    waiting_save = False

    try:
        if m.photo:
            fid = m.photo[-1].file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_photo(ADMIN_ID, d, caption="📸 Сохранено")
            del d
        elif m.video:
            fid = m.video.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_video(ADMIN_ID, d, caption="🎬 Сохранено")
            del d
        elif m.video_note:
            fid = m.video_note.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_video_note(ADMIN_ID, d)
            del d
        elif m.voice:
            fid = m.voice.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_voice(ADMIN_ID, d)
            del d
        elif m.document:
            fid = m.document.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_document(ADMIN_ID, d)
            del d
        elif m.sticker:
            bot.send_sticker(ADMIN_ID, m.sticker.file_id)
        elif m.audio:
            fid = m.audio.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_audio(ADMIN_ID, d)
            del d
        bot.send_message(m.chat.id, "✅ Сохранено")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        send_error_to_admin(f"сейф: {e}")

# ===== АФК =====
def enter_afk():
    global afk_enabled, ADMIN_ID, afk_emoji_id, back_emoji_id
    if afk_enabled:
        return
    afk_enabled = True

    if afk_emoji_id and ADMIN_ID:
        try:
            bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id=afk_emoji_id)
        except Exception as e:
            logger.error(f"Ошибка АФК: {e}")

    if ADMIN_ID:
        bot.send_message(ADMIN_ID, "🌙 АФК включён")

def exit_afk():
    global afk_enabled, ADMIN_ID, back_emoji_id
    if not afk_enabled:
        return
    afk_enabled = False

    if ADMIN_ID:
        try:
            if back_emoji_id:
                bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id=back_emoji_id)
            else:
                bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id="")
        except Exception as e:
            logger.error(f"Ошибка АФК: {e}")
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

# ===== КОМАНДЫ БОТА =====
@bot.message_handler(commands=['afk_on'])
def manual_afk_on(m):
    if m.from_user.id != ADMIN_ID:
        return
    enter_afk()
    bot.send_message(m.chat.id, "АФК включён.")

@bot.message_handler(commands=['afk_off'])
def manual_afk_off(m):
    if m.from_user.id != ADMIN_ID:
        return
    exit_afk()
    global last_activity
    last_activity = time.time()
    bot.send_message(m.chat.id, "АФК выключен.")

@bot.message_handler(commands=['afk_time'])
def set_afk_time(m):
    global afk_timeout
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(m.chat.id, f"Текущее время: {afk_timeout} сек\n/afk_time 300")
        return
    try:
        s = int(parts[1])
        if s < 30 or s > 86400:
            bot.send_message(m.chat.id, "❌ От 30 до 86400 сек.")
            return
        afk_timeout = s
        bot.send_message(m.chat.id, f"✅ Время АФК: {s} сек")
    except ValueError:
        bot.send_message(m.chat.id, "❌ Число.")

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
        f"• Замучено: {len(muted_users)}"
    )
    bot.send_message(m.chat.id, text)

# ===== ХЕЛПЕР =====
def is_command(text, cmd):
    if not text:
        return False
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return False
    return parts[0].lower() == cmd.lower()

# ===== МУТ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "мут")
)
def handle_mute(m):
    cid = m.chat.id
    conn_id = m.business_connection_id

    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    parts = m.text.strip().split(maxsplit=1)
    duration = None
    if len(parts) > 1:
        match = re.match(r'^(\d+)\s*([сcмmчhдd]?)$', parts[1].strip().lower())
        if match:
            v = int(match.group(1))
            u = match.group(2)
            mult = {'с': 1, 'c': 1, 'м': 60, 'm': 60, 'ч': 3600, 'h': 3600, 'д': 86400, 'd': 86400}
            duration = v * mult.get(u, 1)

    target_id = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target_id = m.reply_to_message.from_user.id
    else:
        if cid in chat_partners:
            target_id = chat_partners[cid]["id"]

    if not target_id:
        try:
            bot.send_message(cid, "❌ Не знаю, кого мутить.", business_connection_id=conn_id)
        except:
            pass
        return

    until = time.time() + duration if duration else None
    muted_users[cid] = {"user_id": target_id, "until": until, "conn_id": conn_id}

    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton(
        text="Размут",
        callback_data=f"unmute_{cid}",
        style="success"
    )
    markup.add(btn)

    try:
        bot.send_message(cid, mute_text, entities=mute_entities, reply_markup=markup, business_connection_id=conn_id)
    except:
        try:
            bot.send_message(cid, mute_text, reply_markup=markup, business_connection_id=conn_id)
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("unmute_"))
def callback_unmute(call):
    cid = int(call.data.split("_")[1])

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Только админ.")
        return

    if cid in muted_users:
        del muted_users[cid]
        bot.answer_callback_query(call.id, "🔓 Мут снят")

        try:
            new_text = f'ты размучен пиши)<tg-emoji emoji-id="{UNMUTE_EMOJI_ID}">👋</tg-emoji>'
            bot.edit_message_text(
                chat_id=cid,
                message_id=call.message.message_id,
                text=new_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования: {e}")
            try:
                bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text="ты размучен пиши)")
            except:
                pass

        try:
            bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None)
        except:
            pass
    else:
        bot.answer_callback_query(call.id, "❌ Мут уже снят")

# ===== АНМУТ =====
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
            bot.send_message(cid, "❌ Нет мута", business_connection_id=conn_id)
        except:
            pass

# ===== ВАРН =====
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
        if cid in chat_partners:
            target_id = chat_partners[cid]["id"]

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

# ===== ОБХОД =====
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
            text = f'Обход выключен <tg-emoji emoji-id="{BYPASS_EMOJI_ID}">🔄</tg-emoji>'
            bot.send_message(cid, text, parse_mode="HTML", business_connection_id=conn_id)
        except:
            pass
    else:
        bypass_enabled[cid] = True
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton(
            text="Выключить обход",
            callback_data=f"bypass_off_{cid}",
            style="danger"
        )
        markup.add(btn)
        try:
            text = f'Обход включён <tg-emoji emoji-id="{BYPASS_EMOJI_ID}">🔄</tg-emoji>'
            bot.send_message(cid, text, parse_mode="HTML", reply_markup=markup, business_connection_id=conn_id)
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("bypass_off_"))
def callback_bypass_off(call):
    cid = int(call.data.split("_")[2])

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Только админ.")
        return

    bypass_enabled[cid] = False
    bot.answer_callback_query(call.id, "🛑 Обход выключен")

    try:
        new_text = f'Обход выключен <tg-emoji emoji-id="{BYPASS_EMOJI_ID}">🔄</tg-emoji>'
        bot.edit_message_text(
            chat_id=cid,
            message_id=call.message.message_id,
            text=new_text,
            parse_mode="HTML"
        )
    except:
        pass

    try:
        bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None)
    except:
        pass

# ===== ЭХО =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "эхо")
)
def handle_echo(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    if echo_enabled.get(cid):
        echo_enabled[cid] = False
        try:
            bot.send_message(cid, "🛑 Эхо выключено", business_connection_id=conn_id)
        except:
            pass
    else:
        echo_enabled[cid] = True
        try:
            bot.send_message(cid, "🔊 Эхо включено", business_connection_id=conn_id)
        except:
            pass

# ===== СПАМ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "спам")
)
def handle_spam(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    parts = m.text.strip().split(maxsplit=2)
    if len(parts) < 2:
        try:
            bot.send_message(cid, "❌ Использование: спам слово 5", business_connection_id=conn_id)
        except:
            pass
        return

    word = parts[1]
    count = 15
    if len(parts) >= 3:
        try:
            count = int(parts[2])
        except:
            pass

    if count > 30:
        count = 30
    if count < 1:
        count = 1

    for _ in range(count):
        try:
            bot.send_message(cid, word, business_connection_id=conn_id)
            time.sleep(0.3)
        except:
            break

# ===== АНИМАЦИЯ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and (
        is_command(m.text, "аним") or is_command(m.text, "анимация")
    )
)
def handle_anim(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    parts = m.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return
    text = parts[1]

    try:
        msg = bot.send_message(cid, "•", business_connection_id=conn_id)
    except:
        return

    current = ""
    for char in text:
        current += char
        try:
            bot.edit_message_text(
                current,
                chat_id=cid,
                message_id=msg.message_id,
                business_connection_id=conn_id
            )
        except:
            pass
        time.sleep(0.1)

# ===== ШАР =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "шар")
)
def handle_ball(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    answers = ["да", "нет", "возможно", "скорее нет", "скорее да", "не знаю", "спроси позже"]
    ans = random.choice(answers)

    try:
        bot.send_message(cid, f"🎱 {ans}", business_connection_id=conn_id)
    except:
        pass

# ===== РЕК =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "рек")
)
def handle_rek(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    try:
        msg = bot.send_message(cid, "3...", business_connection_id=conn_id)
    except:
        return

    time.sleep(1)
    try:
        bot.edit_message_text("2...", chat_id=cid, message_id=msg.message_id, business_connection_id=conn_id)
    except:
        pass
    time.sleep(1)
    try:
        bot.edit_message_text("1...", chat_id=cid, message_id=msg.message_id, business_connection_id=conn_id)
    except:
        pass
    time.sleep(1)

    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton(
        text="Тап",
        callback_data=f"rek_tap_{cid}",
        style="success"
    )
    markup.add(btn)

    rek_games[cid] = {"winner": None, "admin_id": ADMIN_ID}

    try:
        bot.edit_message_text(
            "🔥 БЫСТРЕЕ!",
            chat_id=cid,
            message_id=msg.message_id,
            reply_markup=markup,
            business_connection_id=conn_id
        )
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("rek_tap_"))
def callback_rek(call):
    cid = int(call.data.split("_")[2])

    if cid not in rek_games:
        bot.answer_callback_query(call.id, "❌ Игра закончена")
        return

    game = rek_games[cid]
    if game["winner"] is not None:
        bot.answer_callback_query(call.id, "❌ Уже нажали")
        return

    uid = call.from_user.id
    game["winner"] = uid

    bot.answer_callback_query(call.id, "⚡ Ты нажал первым!")

    if uid == ADMIN_ID:
        name = "Ты"
    else:
        name = chat_partners.get(cid, {}).get("name", "Собеседник")

    try:
        bot.edit_message_text(
            f"🏆 Победитель: {name}!",
            chat_id=cid,
            message_id=call.message.message_id
        )
    except:
        pass
    try:
        bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None)
    except:
        pass

    del rek_games[cid]

# ===== РПС =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "рпс")
)
def handle_rps(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    if cid not in chat_partners:
        try:
            bot.send_message(cid, "❌ Собеседник ещё не писал.", business_connection_id=conn_id)
        except:
            pass
        return

    rps_games[cid] = {
        "stage": "admin",
        "admin_id": ADMIN_ID,
        "partner_id": chat_partners[cid]["id"],
        "admin_choice": None,
        "partner_choice": None,
        "msg_id": None
    }

    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("🪨", callback_data=f"rps_admin_камень_{cid}", style="primary"),
        types.InlineKeyboardButton("✂️", callback_data=f"rps_admin_ножницы_{cid}", style="primary"),
        types.InlineKeyboardButton("📃", callback_data=f"rps_admin_бумага_{cid}", style="primary")
    )

    try:
        msg = bot.send_message(
            cid,
            "🎮 РПС: твой ход, хозяин",
            reply_markup=markup,
            business_connection_id=conn_id
        )
        rps_games[cid]["msg_id"] = msg.message_id
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("rps_"))
def callback_rps(call):
    parts = call.data.split("_")
    stage = parts[1]
    choice = parts[2]
    cid = int(parts[3])

    if cid not in rps_games:
        bot.answer_callback_query(call.id, "❌ Игра закончена")
        return

    game = rps_games[cid]
    uid = call.from_user.id

    if stage == "admin":
        if uid != game["admin_id"]:
            bot.answer_callback_query(call.id, "❌ Не твой ход!")
            return
        game["admin_choice"] = choice
        game["stage"] = "partner"

        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🪨", callback_data=f"rps_partner_камень_{cid}", style="primary"),
            types.InlineKeyboardButton("✂️", callback_data=f"rps_partner_ножницы_{cid}", style="primary"),
            types.InlineKeyboardButton("📃", callback_data=f"rps_partner_бумага_{cid}", style="primary")
        )
        try:
            bot.edit_message_text(
                "🎮 РПС: ход собеседника",
                chat_id=cid,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        except:
            pass
        bot.answer_callback_query(call.id, f"✅ Ты выбрал: {choice}")

    elif stage == "partner":
        if uid != game["partner_id"]:
            bot.answer_callback_query(call.id, "❌ Не твой ход!")
            return
        game["partner_choice"] = choice

        admin_c = game["admin_choice"]
        partner_c = choice

        win_map = {"камень": "ножницы", "ножницы": "бумага", "бумага": "камень"}

        if admin_c == partner_c:
            result = "ничья"
        elif win_map[admin_c] == partner_c:
            result = "admin"
        else:
            result = "partner"

        admin_name = bot.get_chat(game["admin_id"]).first_name or "Хозяин"
        partner_name = chat_partners.get(cid, {}).get("name", "Собеседник")

        if result == "admin":
            text = f"🥇 Красавчик {admin_name}! Победа за тобой!"
        elif result == "partner":
            text = f"🥇 Красавчик {partner_name}! Победа за тобой!"
        else:
            text = "🤝 Ничья! Вы оба лучшие."

        try:
            bot.edit_message_text(
                f"{text}\n\n🪨 {admin_c} vs {partner_c}",
                chat_id=cid,
                message_id=call.message.message_id
            )
        except:
            pass
        try:
            bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None)
        except:
            pass

        bot.answer_callback_query(call.id, "✅ Выбор принят")
        del rps_games[cid]

# ===== МОНЕТКА =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "монетка")
)
def handle_coin(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    try:
        msg = bot.send_message(cid, "•", business_connection_id=conn_id)
    except:
        return

    for dots in ["••", "•••"]:
        time.sleep(0.5)
        try:
            bot.edit_message_text(dots, chat_id=cid, message_id=msg.message_id, business_connection_id=conn_id)
        except:
            pass

    time.sleep(0.5)
    result = random.choice(["орёл", "решка"])
    try:
        bot.edit_message_text(f"🪙 Выпал(а) {result}", chat_id=cid, message_id=msg.message_id, business_connection_id=conn_id)
    except:
        pass

# ===== СЕЙФ В БИЗНЕС-ЧАТЕ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "сейф")
)
def handle_save_from_reply(m):
    cid = m.chat.id
    conn_id = m.business_connection_id

    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass

    if not m.reply_to_message:
        try:
            bot.send_message(cid, "❌ Ответь на медиа командой сейф", business_connection_id=conn_id)
        except:
            pass
        return

    replied = m.reply_to_message

    try:
        if replied.photo:
            fid = replied.photo[-1].file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_photo(ADMIN_ID, d, caption=f"📸 Из чата {cid}")
            del d
        elif replied.video:
            fid = replied.video.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_video(ADMIN_ID, d, caption=f"🎬 Из чата {cid}")
            del d
        elif replied.video_note:
            fid = replied.video_note.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_video_note(ADMIN_ID, d)
            del d
        elif replied.voice:
            fid = replied.voice.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_voice(ADMIN_ID, d)
            del d
        elif replied.document:
            fid = replied.document.file_id
            fi = bot.get_file(fid)
            d = bot.download_file(fi.file_path)
            bot.send_document(ADMIN_ID, d)
            del d
        else:
            try:
                bot.copy_message(ADMIN_ID, cid, replied.message_id)
            except Exception as e:
                send_error_to_admin(f"сейф fallback: {e}")
    except Exception as e:
        logger.error(f"Ошибка сейф: {e}")
        try:
            bot.copy_message(ADMIN_ID, cid, replied.message_id)
        except Exception as e2:
            send_error_to_admin(f"сейф: {e2}")

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
            chat_partners[cid] = {
                "id": uid,
                "name": m.from_user.first_name or "Собеседник"
            }

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

            if warn_info["count"] >= warn_limit:
                muted_users[cid] = {"user_id": uid, "until": None, "conn_id": m.business_connection_id}
                del warned_users[cid]
                try:
                    bot.send_message(cid, "🚫 Лимит варнов. Мут навсегда.", business_connection_id=m.business_connection_id)
                except:
                    pass
            else:
                text = warn_text.replace("{count}", str(warn_info["count"])).replace("{limit}", str(warn_limit))
                try:
                    bot.send_message(cid, text, entities=warn_entities, business_connection_id=m.business_connection_id)
                except:
                    try:
                        bot.send_message(cid, text, business_connection_id=m.business_connection_id)
                    except:
                        pass

    # Эхо
    if ADMIN_ID and uid != ADMIN_ID and echo_enabled.get(cid):
        try:
            if m.text:
                bot.send_message(cid, m.text, entities=m.entities, business_connection_id=m.business_connection_id)
            elif m.sticker:
                bot.send_sticker(cid, m.sticker.file_id, business_connection_id=m.business_connection_id)
            elif m.photo:
                bot.send_photo(cid, m.photo[-1].file_id, caption=m.caption, business_connection_id=m.business_connection_id)
            elif m.video:
                bot.send_video(cid, m.video.file_id, caption=m.caption, business_connection_id=m.business_connection_id)
        except:
            pass
        return

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
        except:
            pass
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
    logger.info(f"Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
