import telebot
import time
import threading
import logging
import os
import re
import random
import json
from datetime import datetime, timezone, timedelta
from telebot import types

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")
PASSWORD = "qwer1"
ADMIN_ID = None
ADMIN_NAME = "Хозяин"

AFK_SHORT_THRESHOLD = 5 * 60
AFK_RECHECK_DELAY = 10 * 60

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN, threaded=False)

# ===== СЛОВАРЬ ДЛЯ КРОКОДИЛА =====
WORDS = []
try:
    with open('words.txt', 'r', encoding='utf-8') as f:
        WORDS = [line.strip() for line in f if line.strip()]
    logger.info(f"Загружено слов для Крокодила: {len(WORDS)}")
except Exception as e:
    logger.error(f"Ошибка чтения words.txt: {e}")
    WORDS = ["солнце", "машина", "кошка", "дерево", "собака"]

# ===== ФАЙЛ ДЛЯ ОГНЯ =====
FIRE_FILE = "fire.json"
fire_data = {}

def load_fire():
    global fire_data
    try:
        with open(FIRE_FILE, 'r', encoding='utf-8') as f:
            fire_data = json.load(f)
        logger.info(f"Загружено огней: {len(fire_data)}")
    except:
        fire_data = {}

def save_fire():
    try:
        with open(FIRE_FILE, 'w', encoding='utf-8') as f:
            json.dump(fire_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения fire.json: {e}")

load_fire()

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
bypass_msg_ids = {}

echo_enabled = {}
echo_msg_ids = {}

troll_enabled = {}
troll_texts = []
troll_index = {}
waiting_troll_texts = False
troll_buffer = []

rps_games = {}
rek_games = {}
crocodile_games = {}

# Имитация
imitation_active = {}  # {cid: ["кружок", "видео"]}
imitation_msg_ids = {} # {cid: {"msg_id": ..., "conn_id": ...}}
imitation_timers = {}  # {cid: threading.Timer}

# Формат
format_active = {}  # {cid: ["bold", "italic"]}
format_msg_ids = {}

waiting_save = False

# Time
time_zones = {}  # {ADMIN_ID: offset_hours}
time_thread_running = False

UNMUTE_EMOJI_ID = "5386436816557601037"
BYPASS_EMOJI_ID = "5841243255856960314"
HELLO_EMOJI_ID = "5386436816557601037"
ECHO_EMOJI_ID = "5841243255856960314"

# ===== СПИСОК КОМАНД =====
COMMANDS_LIST = """<b>📋 Список команд</b>

<b>⚙️ Настройки (в личке):</b>
<code>/start</code> — приветствие
<code>/status</code> — статус
<code>/afk_on</code> / <code>/afk_off</code> — АФК
<code>/afk_time 300</code> — время АФК
<code>/set_mute_text</code> — текст мута
<code>/set_warn_text</code> — текст варна
<code>/set_warn_limit 3</code> — лимит варнов
<code>/set_back_emoji</code> — эмодзи возврата
<code>/set_troll_texts</code> — тексты троллинга
<code>/time</code> — часовой пояс в фамилии
<code>/cancel</code> — отмена

<b>🎬 В бизнес-чатах:</b>
<code>мут</code> / <code>мут 10м</code> / <code>анмут</code>
<code>варн</code> — варны
<code>обход</code> — дублирование
<code>эхо</code> — повтор
<code>тролл</code> — троллинг
<code>сейф</code> — медиа в ЛС
<code>спам слово 5</code> — спам
<code>аним текст</code> — по буквам
<code>шар вопрос</code> — шар
<code>инфо</code> — информация
<code>рек</code> / <code>рпс</code> / <code>монетка</code>
<code>крокодил</code> — игра
<code>кружок</code> — видео в кружок
<code>имитация [тип]</code> — имитация
<code>формат [тип]</code> — формат сообщений
<code>огонь</code> / <code>огонь топ</code> / <code>огонь заморозка</code> / <code>огонь разморозка</code> / <code>огонь рестарт</code>"""

# ===== ХЕЛПЕРЫ =====
def plural_days(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} дня"
    else:
        return f"{n} дней"

def plural_messages(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} сообщение"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} сообщения"
    else:
        return f"{n} сообщений"

def is_command(text, cmd):
    if not text:
        return False
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return False
    return parts[0].lower() == cmd.lower()

def send_error_to_admin(text):
    if ADMIN_ID:
        try:
            bot.send_message(ADMIN_ID, f"⚠️ Ошибка:\n{text}")
        except:
            pass

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
    global ADMIN_ID, ADMIN_NAME
    if m.text == PASSWORD:
        user_state[m.from_user.id] = 'authorized'
        ADMIN_ID = m.from_user.id
        ADMIN_NAME = m.from_user.first_name or "Хозяин"
        bot.send_message(m.chat.id, "✅ Пароль принят.")
        send_hello(m.chat.id)
        logger.info(f"Админ: {ADMIN_ID} ({ADMIN_NAME})")
    else:
        bot.send_message(m.chat.id, "❌ Неверный пароль:")

# ===== ЭМОДЗИ АФК =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID 
    and m.text and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities)
    and not waiting_mute_text and not waiting_back_emoji 
    and not waiting_warn_text and not waiting_troll_texts,
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
            bot.send_message(m.chat.id, f"✅ Эмодзи АФК сохранён!\nID: `{afk_emoji_id}`", parse_mode="Markdown")
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
    bot.send_message(m.chat.id, "✅ Сброшено.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and m.text and m.entities 
    and any(e.type == 'custom_emoji' for e in m.entities) and waiting_back_emoji,
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
    bot.send_message(m.chat.id, f"Текущий: {mute_text}\n\nОтправь новый. /cancel — отмена.")

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
    bot.send_message(m.chat.id, f"✅ Сохранено:\n{mute_text}")

# ===== ТЕКСТ ВАРНА =====
@bot.message_handler(commands=['set_warn_text'])
def set_warn_text_cmd(m):
    global waiting_warn_text
    if m.from_user.id != ADMIN_ID:
        return
    waiting_warn_text = True
    bot.send_message(m.chat.id, f"Текущий: {warn_text}\n\nИспользуй <code>{{count}}</code> и <code>{{limit}}</code>.", parse_mode="HTML")

@bot.message_handler(commands=['set_warn_limit'])
def set_warn_limit_cmd(m):
    global warn_limit
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(m.chat.id, f"Лимит: {warn_limit}\n/set_warn_limit 3")
        return
    try:
        limit = int(parts[1])
        if limit < 1 or limit > 100:
            bot.send_message(m.chat.id, "❌ От 1 до 100.")
            return
        warn_limit = limit
        bot.send_message(m.chat.id, f"✅ Лимит: {warn_limit}")
    except ValueError:
        bot.send_message(m.chat.id, "❌ Число.")

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
    bot.send_message(m.chat.id, f"✅ Сохранено:\n{warn_text}")

# ===== ТЕКСТЫ ТРОЛЛИНГА =====
@bot.message_handler(commands=['set_troll_texts'])
def set_troll_texts_cmd(m):
    global waiting_troll_texts, troll_buffer
    if m.from_user.id != ADMIN_ID:
        return
    waiting_troll_texts = True
    troll_buffer = []
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Готово", callback_data="troll_done", style="primary")
    markup.add(btn)
    bot.send_message(m.chat.id, "Отправляй тексты по одному. Когда закончишь — нажми «Готово».", reply_markup=markup)

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and waiting_troll_texts and m.text,
    content_types=['text']
)
def receive_troll_text(m):
    global troll_buffer
    troll_buffer.append(m.text)
    bot.send_message(m.chat.id, f"✅ Добавлен ({len(troll_buffer)}). Ещё или «Готово».")

@bot.callback_query_handler(func=lambda call: call.data == "troll_done")
def callback_troll_done(call):
    global troll_texts, waiting_troll_texts, troll_buffer
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    if not troll_buffer:
        bot.answer_callback_query(call.id, "❌ Нет текстов")
        return
    troll_texts = troll_buffer.copy()
    waiting_troll_texts = False
    troll_buffer = []
    texts = "\n".join([f"{i+1}. {t}" for i, t in enumerate(troll_texts)])
    bot.edit_message_text(f"✅ Сохранено {len(troll_texts)} текстов:\n{texts}", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ===== /time =====
@bot.message_handler(commands=['time'])
def time_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) > 1 and parts[1].lower() == "off":
        if ADMIN_ID in time_zones:
            del time_zones[ADMIN_ID]
        bot.send_message(m.chat.id, "🛑 Время отключено.")
        return

    zones = [("МСК (UTC+3)", 3), ("UTC+0", 0), ("UTC+1", 1), ("UTC+2", 2),
             ("UTC+4", 4), ("UTC+5", 5), ("UTC+6", 6), ("UTC+7", 7),
             ("UTC+8", 8), ("UTC+9", 9), ("UTC+10", 10), ("UTC+11", 11), ("UTC+12", 12)]
    markup = types.InlineKeyboardMarkup(row_width=2)
    for name, offset in zones:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"tz_{offset}", style="primary"))
    bot.send_message(m.chat.id, "🕐 Выбери часовой пояс:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("tz_"))
def callback_tz(call):
    global time_zones
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    offset = int(call.data.split("_")[1])
    time_zones[ADMIN_ID] = offset
    bot.answer_callback_query(call.id, f"✅ UTC+{offset}")
    bot.edit_message_text(f"✅ Часовой пояс: UTC+{offset}\nВремя будет меняться в фамилии каждую минуту.", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ===== СЕЙФ ЛИЧКА =====
@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and m.text and m.text.strip().lower() == "сейф"
)
def save_cmd(m):
    global waiting_save
    waiting_save = True
    bot.send_message(m.chat.id, "Отправь медиа.")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and waiting_save,
    content_types=['photo', 'video', 'document', 'voice', 'sticker', 'audio', 'video_note']
)
def save_media(m):
    global waiting_save
    waiting_save = False
    try:
        if m.photo:
            fi = bot.get_file(m.photo[-1].file_id)
            d = bot.download_file(fi.file_path)
            bot.send_photo(ADMIN_ID, d, caption="📸")
            del d
        elif m.video:
            fi = bot.get_file(m.video.file_id)
            d = bot.download_file(fi.file_path)
            bot.send_video(ADMIN_ID, d, caption="🎬")
            del d
        elif m.video_note:
            fi = bot.get_file(m.video_note.file_id)
            d = bot.download_file(fi.file_path)
            bot.send_video_note(ADMIN_ID, d)
            del d
        elif m.voice:
            fi = bot.get_file(m.voice.file_id)
            d = bot.download_file(fi.file_path)
            bot.send_voice(ADMIN_ID, d)
            del d
        elif m.document:
            fi = bot.get_file(m.document.file_id)
            d = bot.download_file(fi.file_path)
            bot.send_document(ADMIN_ID, d)
            del d
        elif m.sticker:
            bot.send_sticker(ADMIN_ID, m.sticker.file_id)
        elif m.audio:
            fi = bot.get_file(m.audio.file_id)
            d = bot.download_file(fi.file_path)
            bot.send_audio(ADMIN_ID, d)
            del d
        bot.send_message(m.chat.id, "✅ Сохранено")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        send_error_to_admin(f"сейф: {e}")

# ===== /cancel =====
@bot.message_handler(commands=['cancel'])
def cancel_cmd(m):
    global waiting_mute_text, waiting_back_emoji, waiting_warn_text, waiting_save, waiting_troll_texts
    if m.from_user.id != ADMIN_ID:
        return
    waiting_mute_text = False
    waiting_back_emoji = False
    waiting_warn_text = False
    waiting_save = False
    waiting_troll_texts = False
    bot.send_message(m.chat.id, "Отменено.")

# ===== АФК =====
def enter_afk():
    global afk_enabled, ADMIN_ID, afk_emoji_id
    if afk_enabled:
        return
    afk_enabled = True
    if afk_emoji_id and ADMIN_ID:
        try:
            bot.set_user_emoji_status(user_id=ADMIN_ID, emoji_status_custom_emoji_id=afk_emoji_id)
        except Exception as e:
            logger.error(f"АФК: {e}")
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
            logger.error(f"АФК: {e}")
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
    bot.send_message(m.chat.id, "АФК вкл.")

@bot.message_handler(commands=['afk_off'])
def manual_afk_off(m):
    if m.from_user.id != ADMIN_ID:
        return
    exit_afk()
    global last_activity
    last_activity = time.time()
    bot.send_message(m.chat.id, "АФК выкл.")

@bot.message_handler(commands=['afk_time'])
def set_afk_time(m):
    global afk_timeout
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(m.chat.id, f"Время: {afk_timeout} сек")
        return
    try:
        s = int(parts[1])
        if s < 30 or s > 86400:
            bot.send_message(m.chat.id, "❌ 30-86400 сек.")
            return
        afk_timeout = s
        bot.send_message(m.chat.id, f"✅ {s} сек")
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
        f"• Эмодзи АФК: {afk_emoji_id or '—'}\n"
        f"• Возврат: {back_emoji_id or '—'}\n"
        f"• Слов: {len(WORDS)}\n"
        f"• Замучено: {len(muted_users)}\n"
        f"• Огней: {len(fire_data)}"
    )
    bot.send_message(m.chat.id, text)

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
    elif cid in chat_partners:
        target_id = chat_partners[cid]["id"]

    if not target_id:
        try:
            bot.send_message(cid, "❌ Кого мутить?", business_connection_id=conn_id)
        except:
            pass
        return

    until = time.time() + duration if duration else None
    muted_users[cid] = {"user_id": target_id, "until": until, "conn_id": conn_id}

    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Размут", callback_data=f"unmute_{cid}", style="success")
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
        bot.answer_callback_query(call.id, "❌")
        return
    if cid in muted_users:
        conn_id = muted_users[cid].get("conn_id")
        del muted_users[cid]
        bot.answer_callback_query(call.id, "🔓")
        try:
            new_text = f'ты размучен пиши)<tg-emoji emoji-id="{UNMUTE_EMOJI_ID}">👋</tg-emoji>'
            bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text=new_text, parse_mode="HTML", business_connection_id=conn_id)
        except Exception as e:
            logger.error(f"edit: {e}")
        try:
            bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None, business_connection_id=conn_id)
        except:
            pass

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
            bot.send_message(cid, "🔓 Снят", business_connection_id=conn_id)
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
    elif cid in chat_partners:
        target_id = chat_partners[cid]["id"]
    if not target_id:
        return
    warned_users[cid] = {"user_id": target_id, "count": 0}
    try:
        bot.send_message(cid, f"⚠️ Варн. Лимит: {warn_limit}", business_connection_id=conn_id)
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
        if cid in bypass_msg_ids:
            data = bypass_msg_ids[cid]
            try:
                bot.delete_business_messages(data["conn_id"], [data["msg_id"]])
            except:
                pass
            del bypass_msg_ids[cid]
    else:
        bypass_enabled[cid] = True
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("Выключить обход", callback_data=f"bypass_off_{cid}", style="danger")
        markup.add(btn)
        try:
            text = f'Обход включён <tg-emoji emoji-id="{BYPASS_EMOJI_ID}">🔄</tg-emoji>'
            msg = bot.send_message(cid, text, parse_mode="HTML", reply_markup=markup, business_connection_id=conn_id)
            bypass_msg_ids[cid] = {"msg_id": msg.message_id, "conn_id": conn_id}
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("bypass_off_"))
def callback_bypass_off(call):
    cid = int(call.data.split("_")[2])
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    bypass_enabled[cid] = False
    bot.answer_callback_query(call.id, "🛑")
    if cid in bypass_msg_ids:
        data = bypass_msg_ids[cid]
        try:
            bot.delete_business_messages(data["conn_id"], [data["msg_id"]])
        except:
            pass
        del bypass_msg_ids[cid]

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
        if cid in echo_msg_ids:
            data = echo_msg_ids[cid]
            try:
                bot.delete_business_messages(data["conn_id"], [data["msg_id"]])
            except:
                pass
            del echo_msg_ids[cid]
    else:
        echo_enabled[cid] = True
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("Выключить эхо", callback_data=f"echo_off_{cid}", style="danger")
        markup.add(btn)
        try:
            text = f'Эхо включено <tg-emoji emoji-id="{ECHO_EMOJI_ID}">🔊</tg-emoji>'
            msg = bot.send_message(cid, text, parse_mode="HTML", reply_markup=markup, business_connection_id=conn_id)
            echo_msg_ids[cid] = {"msg_id": msg.message_id, "conn_id": conn_id}
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("echo_off_"))
def callback_echo_off(call):
    cid = int(call.data.split("_")[2])
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    echo_enabled[cid] = False
    bot.answer_callback_query(call.id, "🛑")
    if cid in echo_msg_ids:
        data = echo_msg_ids[cid]
        try:
            bot.delete_business_messages(data["conn_id"], [data["msg_id"]])
        except:
            pass
        del echo_msg_ids[cid]

# ===== ТРОЛЛ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "тролл")
)
def handle_troll(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    if troll_enabled.get(cid):
        troll_enabled[cid] = False
        try:
            bot.send_message(cid, "🛑 Троллинг выключен", business_connection_id=conn_id)
        except:
            pass
    else:
        if not troll_texts:
            try:
                bot.send_message(cid, "❌ Сначала настрой тексты: /set_troll_texts", business_connection_id=conn_id)
            except:
                pass
            return
        troll_enabled[cid] = True
        troll_index[cid] = 0
        try:
            bot.send_message(cid, "😈 Троллинг включён", business_connection_id=conn_id)
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
        return
    word = parts[1]
    count = 15
    if len(parts) >= 3:
        try:
            count = int(parts[2])
        except:
            pass
    count = min(count, 30)
    count = max(count, 1)
    for _ in range(count):
        try:
            bot.send_message(cid, word, business_connection_id=conn_id)
            time.sleep(0.3)
        except:
            break

# ===== АНИМАЦИЯ =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and (is_command(m.text, "аним") or is_command(m.text, "анимация"))
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
            bot.edit_message_text(current, chat_id=cid, message_id=msg.message_id, business_connection_id=conn_id)
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
    try:
        bot.send_message(cid, f"🎱 {random.choice(answers)}", business_connection_id=conn_id)
    except:
        pass

# ===== ИНФО =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "инфо")
)
def handle_info(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    target = None
    if m.reply_to_message and m.reply_to_message.from_user:
        target = m.reply_to_message.from_user
    elif cid in chat_partners:
        try:
            target = bot.get_chat(chat_partners[cid]["id"])
        except:
            pass
    if not target:
        return
    name = target.first_name or "—"
    if hasattr(target, 'last_name') and target.last_name:
        name += f" {target.last_name}"
    username = f"@{target.username}" if hasattr(target, 'username') and target.username else "нет"
    uid = target.id
    is_prem = "✅" if hasattr(target, 'is_premium') and target.is_premium else "❌"
    text = (
        f"👤 <b>Информация</b>\n\n"
        f"📝 Имя: <code>{name}</code>\n"
        f"🔗 Юзернейм: <code>{username}</code>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"⭐ Premium: {is_prem}"
    )
    try:
        bot.send_message(cid, text, parse_mode="HTML", business_connection_id=conn_id)
    except Exception as e:
        logger.error(f"инфо: {e}")

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
    btn = types.InlineKeyboardButton("Тап", callback_data=f"rek_tap_{cid}", style="success")
    markup.add(btn)
    rek_games[cid] = {"winner": None, "admin_id": ADMIN_ID, "admin_name": ADMIN_NAME, "conn_id": conn_id}
    try:
        bot.edit_message_text("🔥 БЫСТРЕЕ!", chat_id=cid, message_id=msg.message_id, reply_markup=markup, business_connection_id=conn_id)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("rek_tap_"))
def callback_rek(call):
    cid = int(call.data.split("_")[2])
    if cid not in rek_games:
        bot.answer_callback_query(call.id, "❌")
        return
    game = rek_games[cid]
    if game["winner"] is not None:
        bot.answer_callback_query(call.id, "❌")
        return
    uid = call.from_user.id
    game["winner"] = uid
    conn_id = game.get("conn_id")
    bot.answer_callback_query(call.id, "⚡")
    if uid == ADMIN_ID:
        name = game["admin_name"]
    else:
        name = chat_partners.get(cid, {}).get("name", "Собеседник")
    try:
        bot.edit_message_text(f"🏆 {name} победил!", chat_id=cid, message_id=call.message.message_id, business_connection_id=conn_id)
    except:
        pass
    try:
        bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None, business_connection_id=conn_id)
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
        return
    rps_games[cid] = {
        "stage": "admin", "admin_id": ADMIN_ID, "admin_name": ADMIN_NAME,
        "partner_id": chat_partners[cid]["id"], "partner_name": chat_partners[cid]["name"],
        "admin_choice": None, "partner_choice": None, "conn_id": conn_id
    }
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("🪨", callback_data=f"rps_admin_камень_{cid}", style="primary"),
        types.InlineKeyboardButton("✂️", callback_data=f"rps_admin_ножницы_{cid}", style="primary"),
        types.InlineKeyboardButton("📃", callback_data=f"rps_admin_бумага_{cid}", style="primary")
    )
    try:
        bot.send_message(cid, f"🎮 РПС: твой ход, {ADMIN_NAME}", reply_markup=markup, business_connection_id=conn_id)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("rps_"))
def callback_rps(call):
    parts = call.data.split("_")
    stage = parts[1]
    choice = parts[2]
    cid = int(parts[3])
    if cid not in rps_games:
        bot.answer_callback_query(call.id, "❌")
        return
    game = rps_games[cid]
    uid = call.from_user.id
    conn_id = game.get("conn_id")
    if stage == "admin":
        if uid != game["admin_id"]:
            bot.answer_callback_query(call.id, "❌")
            return
        if game["admin_choice"] is not None:
            bot.answer_callback_query(call.id, "❌")
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
            bot.edit_message_text(f"🎮 РПС: ход {game['partner_name']}", chat_id=cid, message_id=call.message.message_id, reply_markup=markup, business_connection_id=conn_id)
        except:
            pass
        bot.answer_callback_query(call.id, f"✅")
    elif stage == "partner":
        if uid != game["partner_id"]:
            bot.answer_callback_query(call.id, "❌")
            return
        if game["partner_choice"] is not None:
            bot.answer_callback_query(call.id, "❌")
            return
        game["partner_choice"] = choice
        admin_c = game["admin_choice"]
        partner_c = choice
        win_map = {"камень": "ножницы", "ножницы": "бумага", "бумага": "камень"}
        if admin_c == partner_c:
            text = "🤝 Ничья! Вы оба лучшие."
        elif win_map[admin_c] == partner_c:
            text = f"🥇 Красавчик {game['admin_name']}! Победа за тобой!"
        else:
            text = f"🥇 Красавчик {game['partner_name']}! Победа за тобой!"
        try:
            bot.edit_message_text(f"{text}\n\n{admin_c} vs {partner_c}", chat_id=cid, message_id=call.message.message_id, business_connection_id=conn_id)
        except:
            pass
        try:
            bot.edit_message_reply_markup(chat_id=cid, message_id=call.message.message_id, reply_markup=None, business_connection_id=conn_id)
        except:
            pass
        bot.answer_callback_query(call.id, "✅")
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

# ===== КРОКОДИЛ =====
def croco_markup(cid):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👀", callback_data=f"croco_show_{cid}", style="primary"),
        types.InlineKeyboardButton("🔃", callback_data=f"croco_change_{cid}", style="danger")
    )
    return markup

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "крокодил")
)
def handle_crocodile(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    if cid not in chat_partners:
        try:
            bot.send_message(cid, "❌ Собеседник не писал.", business_connection_id=conn_id)
        except:
            pass
        return
    word = random.choice(WORDS) if WORDS else "солнце"
    crocodile_games[cid] = {
        "leader_id": ADMIN_ID, "leader_name": ADMIN_NAME,
        "guesser_id": chat_partners[cid]["id"], "guesser_name": chat_partners[cid]["name"],
        "word": word, "msg_id": None, "conn_id": conn_id
    }
    text = f"🐊 Игра «Крокодил» начата!\n\n🎯 Угадывает: {chat_partners[cid]['name']}\n👑 Ведущий: {ADMIN_NAME}"
    try:
        msg = bot.send_message(cid, text, reply_markup=croco_markup(cid), business_connection_id=conn_id)
        crocodile_games[cid]["msg_id"] = msg.message_id
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("croco_"))
def callback_crocodile(call):
    parts = call.data.split("_")
    action = parts[1]
    cid = int(parts[2])
    if cid not in crocodile_games:
        bot.answer_callback_query(call.id, "❌")
        return
    game = crocodile_games[cid]
    uid = call.from_user.id
    if uid != game["leader_id"]:
        bot.answer_callback_query(call.id, "❌ Только ведущий!", show_alert=True)
        return
    if action == "show":
        bot.answer_callback_query(call.id, f"🎯 Слово: {game['word']}", show_alert=True)
    elif action == "change":
        new_word = random.choice(WORDS) if WORDS else "солнце"
        game["word"] = new_word
        try:
            text = f"🐊 Игра «Крокодил»\n\n🎯 Угадывает: {game['guesser_name']}\n👑 Ведущий: {game['leader_name']}\n🔄 Новое слово установлено"
            bot.edit_message_text(text, chat_id=cid, message_id=call.message.message_id, reply_markup=croco_markup(cid), business_connection_id=game.get("conn_id"))
        except:
            pass
        bot.answer_callback_query(call.id, f"🔄 Новое слово: {new_word}", show_alert=True)

# ===== КРУЖОК =====
@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "кружок")
)
def handle_circle(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    if not m.reply_to_message or not m.reply_to_message.video:
        try:
            bot.send_message(cid, "❌ Ответь на видео.", business_connection_id=conn_id)
        except:
            pass
        return
    video = m.reply_to_message.video
    if video.duration and video.duration > 60:
        try:
            bot.send_message(cid, "❌ Видео не подходит для кружка (макс. 1 минута)", business_connection_id=conn_id)
        except:
            pass
        return
    try:
        fi = bot.get_file(video.file_id)
        d = bot.download_file(fi.file_path)
        bot.send_video_note(cid, d, business_connection_id=conn_id)
        del d
    except Exception as e:
        logger.error(f"кружок: {e}")
        try:
            bot.send_message(cid, "❌ Видео не подходит для кружка", business_connection_id=conn_id)
        except:
            pass

# ===== ИМИТАЦИЯ =====
def imitation_worker(cid, conn_id):
    """Фоновый поток, меняет chat_action каждые 4 сек"""
    start = time.time()
    idx = 0
    while cid in imitation_active and imitation_active[cid]:
        if time.time() - start > 3 * 60 * 60:
            break
        actions = imitation_active[cid]
        if not actions:
            break
        action = actions[idx % len(actions)]
        try:
            bot.send_chat_action(cid, action, business_connection_id=conn_id)
        except:
            pass
        idx += 1
        time.sleep(4)
    if cid in imitation_active:
        del imitation_active[cid]

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "имитация")
)
def handle_imitation(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    parts = m.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        help_text = (
            "📩 Использование имитации\n\n"
            "<code>имитация кружок</code> — имитация кружка\n"
            "<code>имитация видео</code> — имитация видео\n"
            "<code>имитация голосовое</code> — имитация голосового\n"
            "<code>имитация фото</code> — имитация фото\n"
            "<code>имитация файл</code> — имитация файла\n"
            "<code>имитация стикер</code> — имитация стикера\n"
            "<code>имитация геолокация</code> — имитация геолокации\n"
            "<code>имитация</code> — остановить"
        )
        try:
            bot.send_message(ADMIN_ID, help_text, parse_mode="HTML")
        except:
            pass
        return
    sub = parts[1].strip().lower()
    mapping = {
        "кружок": "record_video_note",
        "видео": "upload_video",
        "голосовое": "record_voice",
        "фото": "upload_photo",
        "файл": "upload_document",
        "стикер": "choose_sticker",
        "геолокация": "find_location"
    }
    if sub not in mapping:
        try:
            bot.send_message(ADMIN_ID, "❌ Неизвестный тип.")
        except:
            pass
        return
    if cid not in imitation_active:
        imitation_active[cid] = []
    if len(imitation_active[cid]) >= 3:
        try:
            bot.send_message(ADMIN_ID, "❌ Максимум 3 имитации.")
        except:
            pass
        return
    imitation_active[cid].append(mapping[sub])
    if cid not in imitation_timers or not imitation_timers.get(cid, {}).get("running"):
        imitation_timers[cid] = {"running": True}
        threading.Thread(target=imitation_worker, args=(cid, conn_id), daemon=True).start()
    if cid in imitation_msg_ids:
        try:
            bot.edit_message_text(
                f"✅ Имитации: {len(imitation_active[cid])}/3",
                chat_id=ADMIN_ID,
                message_id=imitation_msg_ids[cid]["msg_id"]
            )
        except:
            pass
    else:
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("Выключить", callback_data=f"imitation_off_{cid}", style="danger")
        markup.add(btn)
        try:
            msg = bot.send_message(ADMIN_ID, f"✅ Имитации: {len(imitation_active[cid])}/3", reply_markup=markup)
            imitation_msg_ids[cid] = {"msg_id": msg.message_id}
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("imitation_off_"))
def callback_imitation_off(call):
    cid = int(call.data.split("_")[2])
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    if cid in imitation_active:
        del imitation_active[cid]
    if cid in imitation_timers:
        imitation_timers[cid]["running"] = False
    bot.answer_callback_query(call.id, "🛑")
    try:
        bot.edit_message_text("🛑 Имитация выключена", chat_id=ADMIN_ID, message_id=call.message.message_id)
    except:
        pass
    if cid in imitation_msg_ids:
        del imitation_msg_ids[cid]

# ===== ФОРМАТ =====
FORMAT_MAP = {
    "жирный": ("b", "<b>", "</b>"),
    "курсив": ("i", "<i>", "</i>"),
    "подчёркнутый": ("u", "<u>", "</u>"),
    "зачёркнутый": ("s", "<s>", "</s>"),
    "спойлер": ("spoiler", "<tg-spoiler>", "</tg-spoiler>"),
}

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "формат")
)
def handle_format(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    parts = m.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        try:
            bot.send_message(ADMIN_ID, "❌ /формат жирный | курсив | подчёркнутый | зачёркнутый | спойлер")
        except:
            pass
        return
    sub = parts[1].strip().lower()
    if sub in ("off", "обычный"):
        if cid in format_active:
            del format_active[cid]
        try:
            bot.send_message(ADMIN_ID, "🛑 Формат выключен")
        except:
            pass
        return
    if sub not in FORMAT_MAP:
        try:
            bot.send_message(ADMIN_ID, "❌ Неизвестный формат.")
        except:
            pass
        return
    if cid not in format_active:
        format_active[cid] = []
    if sub in format_active[cid]:
        format_active[cid].remove(sub)
    else:
        format_active[cid].append(sub)
    names = ", ".join(format_active[cid]) if format_active[cid] else "нет"
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Выключить", callback_data=f"format_off_{cid}", style="danger")
    markup.add(btn)
    try:
        if cid in format_msg_ids:
            try:
                bot.edit_message_text(f"✅ Формат: {names}", chat_id=ADMIN_ID, message_id=format_msg_ids[cid], reply_markup=markup)
            except:
                msg = bot.send_message(ADMIN_ID, f"✅ Формат: {names}", reply_markup=markup)
                format_msg_ids[cid] = msg.message_id
        else:
            msg = bot.send_message(ADMIN_ID, f"✅ Формат: {names}", reply_markup=markup)
            format_msg_ids[cid] = msg.message_id
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("format_off_"))
def callback_format_off(call):
    cid = int(call.data.split("_")[2])
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    if cid in format_active:
        del format_active[cid]
    bot.answer_callback_query(call.id, "🛑")
    try:
        bot.edit_message_text("🛑 Формат выключен", chat_id=ADMIN_ID, message_id=call.message.message_id)
    except:
        pass
    if cid in format_msg_ids:
        del format_msg_ids[cid]

# ===== ОГОНЬ =====
def get_fire(cid):
    key = str(cid)
    if key not in fire_data:
        fire_data[key] = {
            "streak": 0, "record": 0,
            "total_bot": 0, "total_partner": 0,
            "last_day": None, "last_msg_time": 0,
            "frozen_until": 0, "freeze_used_month": None,
            "restore_used": [], "restore_until": 0, "broken": False
        }
    return fire_data[key]

def fire_text(cid, partner_name):
    f = get_fire(cid)
    restore_count = len(f.get("restore_used", []))
    freeze_used = 1 if f.get("freeze_used_month") else 0
    restore_left = max(0, 3 - restore_count)
    freeze_left = max(0, 1 - freeze_used)
    return (
        f"🔥 Серия с {partner_name}\n\n"
        f"📅 Дней подряд: {plural_days(f['streak'])}\n"
        f"🏆 Рекорд: {plural_days(f['record'])}\n"
        f"💬 Всего сообщений: {plural_messages(f['total_bot'] + f['total_partner'])}\n\n"
        f"👤 Пользователь бота: {plural_messages(f['total_bot'])}\n"
        f"👤 Собеседник: {plural_messages(f['total_partner'])}\n\n"
        f"🔄 Восстановлений: {restore_left}/3\n"
        f"❄️ Заморозок: {freeze_left}/1"
    )

@bot.business_message_handler(
    func=lambda m: m.text and m.from_user.id == ADMIN_ID and is_command(m.text, "огонь")
)
def handle_fire(m):
    cid = m.chat.id
    conn_id = m.business_connection_id
    parts = m.text.strip().split(maxsplit=1)
    sub = parts[1].strip().lower() if len(parts) > 1 else ""
    partner_name = chat_partners.get(cid, {}).get("name", "Собеседник")

    if sub == "топ":
        try:
            bot.delete_business_messages(conn_id, [m.message_id])
        except:
            pass
        sorted_fires = sorted(fire_data.items(), key=lambda x: x[1].get("streak", 0), reverse=True)
        if not sorted_fires:
            bot.send_message(cid, "❌ Нет серий.", business_connection_id=conn_id)
            return
        lines = ["🔥 <b>Ваши серии</b>\n"]
        medals = ["🥇", "🥈", "🥉"]
        best_name = ""
        best_streak = 0
        best_msgs = 0
        blockquote = []
        for i, (cid_key, f) in enumerate(sorted_fires[:20]):
            name = chat_partners.get(int(cid_key), {}).get("name", "—")
            if i < 3:
                lines.append(f"{medals[i]} 🔥 {name}\n    └ {plural_days(f['streak'])} • {plural_messages(f['total_bot'] + f['total_partner'])}")
            else:
                blockquote.append(f"{i+1}. 🔥 {name}\n    └ {plural_days(f['streak'])} • {plural_messages(f['total_bot'] + f['total_partner'])}")
            if f['streak'] > best_streak:
                best_streak = f['streak']
                best_name = name
                best_msgs = f['total_bot'] + f['total_partner']
        if blockquote:
            lines.append("\n<blockquote>" + "\n".join(blockquote) + "</blockquote>")
        lines.append(f"\n🏆 Лучшая серия: {best_name}")
        lines.append(f"📅 {plural_days(best_streak)} • 💬 {plural_messages(best_msgs)}")
        try:
            bot.send_message(cid, "\n".join(lines), parse_mode="HTML", business_connection_id=conn_id)
        except Exception as e:
            logger.error(f"топ: {e}")
        return

    if sub == "заморозка":
        f = get_fire(cid)
        now = datetime.now()
        month_key = f"{now.year}-{now.month}"
        if f.get("freeze_used_month") == month_key:
            try:
                bot.delete_business_messages(conn_id, [m.message_id])
            except:
                pass
            bot.send_message(cid, "❌ Заморозка уже использована в этом месяце.", business_connection_id=conn_id)
            return
        f["freeze_used_month"] = month_key
        f["frozen_until"] = time.time() + 3 * 24 * 60 * 60
        save_fire()
        try:
            bot.delete_business_messages(conn_id, [m.message_id])
        except:
            pass
        unfreeze_date = datetime.fromtimestamp(f["frozen_until"]).strftime("%d.%m.%Y %H:%M")
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("Разморозить", callback_data=f"fire_unfreeze_{cid}", style="danger")
        markup.add(btn)
        text = (
            f"❄️ <b><u>Серия заморожена!</u></b>\n\n"
            f"Серия заморожена на 3 дня.\n"
            f"Разморозится автоматически: {unfreeze_date}\n\n"
            f"Используйте <code>огонь разморозка</code> для досрочной разморозки."
        )
        try:
            bot.send_message(cid, text, parse_mode="HTML", reply_markup=markup, business_connection_id=conn_id)
        except:
            pass
        return

    if sub == "разморозка":
        f = get_fire(cid)
        if f.get("frozen_until", 0) > time.time():
            f["frozen_until"] = 0
            save_fire()
            try:
                bot.delete_business_messages(conn_id, [m.message_id])
            except:
                pass
            next_month = datetime.now().replace(day=1) + timedelta(days=32)
            next_month_str = next_month.strftime("%d.%m.%Y")
            text = (
                f"🔥 Серия разморожена!\n\n"
                f"<blockquote>Серия заморожена на 3 дня.</blockquote>\n\n"
                f"Серия снова активна.\n"
                f"Следующая заморозка доступна с: {next_month_str}"
            )
            try:
                bot.send_message(cid, text, parse_mode="HTML", business_connection_id=conn_id)
            except:
                pass
        return

    if sub == "рестарт":
        try:
            bot.delete_business_messages(conn_id, [m.message_id])
        except:
            pass
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("Да", callback_data=f"fire_restart_yes_{cid}", style="success"),
            types.InlineKeyboardButton("Нет", callback_data=f"fire_restart_no_{cid}", style="danger")
        )
        try:
            bot.send_message(cid, "Вы точно хотите удалить серию?", reply_markup=markup, business_connection_id=conn_id)
        except:
            pass
        return

    # Обычный огонь
    try:
        bot.delete_business_messages(conn_id, [m.message_id])
    except:
        pass
    f = get_fire(cid)
    try:
        bot.send_message(cid, fire_text(cid, partner_name), business_connection_id=conn_id)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("fire_unfreeze_"))
def callback_fire_unfreeze(call):
    cid = int(call.data.split("_")[2])
    if call.from_user.id not in (ADMIN_ID, chat_partners.get(cid, {}).get("id")):
        bot.answer_callback_query(call.id, "❌")
        return
    f = get_fire(cid)
    if f.get("frozen_until", 0) > time.time():
        f["frozen_until"] = 0
        save_fire()
        next_month = datetime.now().replace(day=1) + timedelta(days=32)
        next_month_str = next_month.strftime("%d.%m.%Y")
        text = (
            f"🔥 Серия разморожена!\n\n"
            f"<blockquote>Серия заморожена на 3 дня.</blockquote>\n\n"
            f"Серия снова активна.\n"
            f"Следующая заморозка доступна с: {next_month_str}"
        )
        try:
            bot.edit_message_text(text, chat_id=cid, message_id=call.message.message_id, parse_mode="HTML")
        except:
            pass
        bot.answer_callback_query(call.id, "🔥")

@bot.callback_query_handler(func=lambda call: call.data.startswith("fire_restart_"))
def callback_fire_restart(call):
    parts = call.data.split("_")
    action = parts[2]
    cid = int(parts[3])
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌")
        return
    if action == "yes":
        # Отправляем второе сообщение собеседнику
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("Да", callback_data=f"fire_restart_partner_yes_{cid}", style="success"),
            types.InlineKeyboardButton("Нет", callback_data=f"fire_restart_partner_no_{cid}", style="danger")
        )
        try:
            bot.edit_message_text(
                f"{ADMIN_NAME} хочет удалить серию. Согласны?",
                chat_id=cid,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        except:
            pass
        bot.answer_callback_query(call.id, "✅")
    elif action == "no":
        bot.answer_callback_query(call.id, "❌")
        partner_name = chat_partners.get(cid, {}).get("name", "Собеседник")
        try:
            bot.edit_message_text(fire_text(cid, partner_name), chat_id=cid, message_id=call.message.message_id)
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("fire_restart_partner_"))
def callback_fire_restart_partner(call):
    parts = call.data.split("_")
    action = parts[3]
    cid = int(parts[4])
    partner_id = chat_partners.get(cid, {}).get("id")
    if call.from_user.id != partner_id:
        bot.answer_callback_query(call.id, "❌")
        return
    if action == "yes":
        f = get_fire(cid)
        old_record = f["record"]
        f["streak"] = 0
        f["record"] = 0
        f["total_bot"] = 0
        f["total_partner"] = 0
        save_fire()
        partner_name = chat_partners.get(cid, {}).get("name", "Собеседник")
        text = (
            f"🔄 Серия перезапущена!\n\n"
            f"<blockquote>Серия сброшена.</blockquote>\n\n"
            f"Серия с {partner_name} начинается заново.\n"
            f"Ваш рекорд ({plural_days(old_record)}) удалён!"
        )
        try:
            bot.edit_message_text(text, chat_id=cid, message_id=call.message.message_id, parse_mode="HTML")
        except:
            pass
        bot.answer_callback_query(call.id, "🔄")
    elif action == "no":
        bot.answer_callback_query(call.id, "❌")
        partner_name = chat_partners.get(cid, {}).get("name", "Собеседник")
        try:
            bot.edit_message_text(fire_text(cid, partner_name), chat_id=cid, message_id=call.message.message_id)
        except:
            pass

# ===== /start =====
@bot.message_handler(commands=['start'])
def start_cmd_2(m):
    pass

# ===== BUSINESS =====
@bot.business_message_handler(func=lambda m: True)
def handle_business(m):
    global business_conn_id, muted_users, chat_partners, warned_users

    business_conn_id = m.business_connection_id
    cid = m.chat.id
    uid = m.from_user.id

    if ADMIN_ID and uid != ADMIN_ID:
        chat_partners[cid] = {"id": uid, "name": m.from_user.first_name or "Собеседник"}

    # ==== ОГОНЬ: счётчики ====
    if ADMIN_ID:
        f = get_fire(cid)
        today = datetime.now().strftime("%Y-%m-%d")
        if uid == ADMIN_ID:
            f["total_bot"] = f.get("total_bot", 0) + 1
        elif uid == chat_partners.get(cid, {}).get("id"):
            f["total_partner"] = f.get("total_partner", 0) + 1
        f["last_msg_time"] = time.time()
        # Простая логика: если оба писали сегодня — +1 день
        if f.get("last_day") != today:
            if f.get("last_day") and f.get("streak", 0) > 0:
                # Проверяем, что оба писали вчера
                pass
            f["last_day"] = today
        save_fire()

    # ==== МУТ (все типы) ====
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

    # ==== ВАРНЫ ====
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
                    pass

    # ==== ТРОЛЛ ====
    if ADMIN_ID and uid != ADMIN_ID and troll_enabled.get(cid) and troll_texts:
        idx = troll_index.get(cid, 0)
        text = troll_texts[idx % len(troll_texts)]
        troll_index[cid] = idx + 1
        def send_troll():
            time.sleep(1)
            try:
                bot.send_message(cid, text, business_connection_id=m.business_connection_id)
            except:
                pass
        threading.Thread(target=send_troll, daemon=True).start()

    # ==== ЭХО ====
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

    # ==== ОБХОД ====
    if ADMIN_ID and uid == ADMIN_ID and bypass_enabled.get(cid):
        try:
            bot.delete_business_messages(m.business_connection_id, [m.message_id])
        except:
            pass
        try:
            if m.text:
                bot.send_message(cid, m.text, entities=m.entities, business_connection_id=m.business_connection_id)
            else:
                bot.copy_message(chat_id=cid, from_chat_id=cid, message_id=m.message_id, business_connection_id=m.business_connection_id)
        except Exception as e:
            logger.error(f"обход: {e}")
        return

    # ==== ФОРМАТ ====
    if ADMIN_ID and uid == ADMIN_ID and format_active.get(cid):
        if m.text:
            tags_open = ""
            tags_close = ""
            for name in format_active[cid]:
                if name in FORMAT_MAP:
                    _, o, c = FORMAT_MAP[name]
                    tags_open += o
                    tags_close = c + tags_close
            formatted = tags_open + m.text + tags_close
            try:
                bot.delete_business_messages(m.business_connection_id, [m.message_id])
            except:
                pass
            try:
                bot.send_message(cid, formatted, parse_mode="HTML", business_connection_id=m.business_connection_id)
            except:
                pass
            return

    # ==== КРОКОДИЛ ====
    if cid in crocodile_games:
        game = crocodile_games[cid]
        if uid == game["guesser_id"] and m.text:
            if m.text.strip().lower() == game["word"].lower():
                old_guesser = game["guesser_name"]
                old_leader_id = game["leader_id"]
                old_leader_name = game["leader_name"]
                old_msg_id = game.get("msg_id")
                # Удаляем старое сообщение
                if old_msg_id:
                    try:
                        bot.delete_business_messages(m.business_connection_id, [old_msg_id])
                    except:
                        pass
                # Меняем роли
                game["leader_id"] = game["guesser_id"]
                game["leader_name"] = game["guesser_name"]
                game["guesser_id"] = old_leader_id
                game["guesser_name"] = old_leader_name
                game["word"] = random.choice(WORDS) if WORDS else "солнце"
                text = (
                    f"🎉 {old_guesser} угадал слово: <b>{m.text.strip()}</b>!\n\n"
                    f"🐊 Продолжаем!\n"
                    f"🎯 Угадывает: {game['guesser_name']}\n"
                    f"👑 Ведущий: {game['leader_name']}"
                )
                try:
                    msg = bot.send_message(cid, text, parse_mode="HTML", reply_markup=croco_markup(cid), business_connection_id=m.business_connection_id)
                    game["msg_id"] = msg.message_id
                except:
                    pass
                return

    if ADMIN_ID and uid == ADMIN_ID:
        global last_activity, afk_enabled
        last_activity = time.time()
        if afk_enabled:
            exit_afk()

# ===== TIME THREAD =====
def time_watcher():
    global time_zones, business_conn_id
    last_set = {}
    while True:
        time.sleep(30)
        if not ADMIN_ID:
            continue
        offset = time_zones.get(ADMIN_ID)
        if offset is None:
            continue
        try:
            tz = timezone(timedelta(hours=offset))
            now = datetime.now(tz).strftime("%H:%M")
            if last_set.get(ADMIN_ID) == now:
                continue
            last_set[ADMIN_ID] = now
            try:
                chat = bot.get_chat(ADMIN_ID)
                first_name = chat.first_name or ADMIN_NAME
                # Нужен business_connection_id
                if business_conn_id:
                    bot.set_business_account_name(
                        business_connection_id=business_conn_id,
                        first_name=first_name,
                        last_name=now
                    )
            except Exception as e:
                logger.error(f"time: {e}")
        except Exception as e:
            logger.error(f"time_watcher: {e}")

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
    threading.Thread(target=time_watcher, daemon=True).start()

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
