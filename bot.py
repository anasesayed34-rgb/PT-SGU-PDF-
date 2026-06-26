"""
PT SGU PDF Bot - النسخة الاحترافية المتكاملة
كلية العلاج الطبيعي - جامعة الصالحية الجديدة
"""

import os
import logging
import sqlite3
import json
import random
import string
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ==============================================
# 1. الإعدادات الأساسية (ضع التوكن هنا)
# ==============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "123456789").split(",") if x.strip()]
DB_PATH = "pt_sgu_pro.db"

# المواد الدراسية (قابلة للتعديل)
SUBJECTS = [
    "Anatomy", "Physiology", "Biophysics", "Biochemistry",
    "Kinesiology", "Manual Muscle Testing", "Neuroanatomy",
    "Pathology", "Pharmacology", "Psychology"
]

# خطط الاشتراك (تجريبية)
SUBSCRIPTION_PLANS = {
    "free": {"name": "مجاني", "max_downloads": 5, "price": 0},
    "premium": {"name": "بريميوم شهري", "max_downloads": 999, "price": 50},
    "vip": {"name": "VIP سنوي", "max_downloads": 9999, "price": 400},
}

# حالات المحادثة
CHOOSING_SUBJECT, CHOOSING_TYPE, ENTERING_TITLE, ENTERING_DESC, ENTERING_TAGS, RECEIVING_FILE = range(6)
AWAITING_ANNOUNCEMENT = 10
AWAITING_WELCOME_MSG = 20
AWAITING_ADD_ADMIN = 30
AWAITING_REMOVE_ADMIN = 31

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================
# 2. قاعدة البيانات المتكاملة
# ==============================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE, username TEXT, first_name TEXT, last_name TEXT,
        joined_at TEXT, is_admin INTEGER DEFAULT 0, 
        subscription_type TEXT DEFAULT 'free', subscription_expiry TEXT,
        referral_code TEXT UNIQUE, referred_by INTEGER, downloads_count INTEGER DEFAULT 0,
        language TEXT DEFAULT 'ar'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT, content_type TEXT, title TEXT, description TEXT,
        file_id TEXT, file_name TEXT, tags TEXT,
        uploaded_by INTEGER, uploaded_at TEXT, downloads INTEGER DEFAULT 0,
        is_public INTEGER DEFAULT 1, requires_subscription INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS downloads_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER, user_id INTEGER, downloaded_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER, referred_id INTEGER, referred_at TEXT, reward_given INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT, created_at TEXT, sent_to INTEGER DEFAULT 0
    )""")
    # إعدادات افتراضية
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_message', 'مرحباً بك في بوت PT SGU!\\nاختر من القائمة أدناه.')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_channel', '')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('items_per_page', '5')")
    conn.commit()
    conn.close()

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, params)
    result = None
    if fetchone:
        result = c.fetchone()
    elif fetchall:
        result = c.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return result

# دوال مساعدة للـ DB
def get_user(user_id):
    return db_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)

def create_user(user_id, username, first_name, last_name, referred_by=None):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return db_query(
        "INSERT INTO users (user_id, username, first_name, last_name, joined_at, referral_code, referred_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, first_name, last_name, datetime.now().isoformat(), code, referred_by),
        commit=True
    )

def is_admin(user_id):
    user = get_user(user_id)
    return user and user[6] == 1

def get_all_users():
    return db_query("SELECT user_id, username, first_name FROM users", fetchall=True)

def get_stats():
    users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    files = db_query("SELECT COUNT(*) FROM files", fetchone=True)[0]
    downloads = db_query("SELECT COUNT(*) FROM downloads_log", fetchone=True)[0]
    premium = db_query("SELECT COUNT(*) FROM users WHERE subscription_type != 'free'", fetchone=True)[0]
    return users, files, downloads, premium

# ==============================================
# 3. دوال إنشاء لوحات المفاتيح (Keyboards)
# ==============================================
def main_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📚 المواد الدراسية", callback_data="show_subjects")],
        [InlineKeyboardButton("🔍 بحث متقدم", callback_data="search_menu")],
        [InlineKeyboardButton("👤 حسابي", callback_data="my_profile")],
        [InlineKeyboardButton("⭐ نظام الإحالة", callback_data="referral_menu")],
        [InlineKeyboardButton("📢 الإعلانات", callback_data="show_announcements")],
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم (أدمن)", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 إدارة الملفات", callback_data="admin_files")],
        [InlineKeyboardButton("📢 إرسال إعلان", callback_data="admin_announce")],
        [InlineKeyboardButton("🧩 الإضافات (Extensions)", callback_data="admin_extensions")],
        [InlineKeyboardButton("⚙️ المتغيرات", callback_data="admin_variables")],
        [InlineKeyboardButton("🔧 إعدادات البوت", callback_data="admin_settings")],
        [InlineKeyboardButton("🔗 نظام الإحالة (تفاصيل)", callback_data="admin_referrals")],
        [InlineKeyboardButton("📄 ترقيم الصفحات", callback_data="admin_pagination")],
        [InlineKeyboardButton("📢 القنوات والمجموعات", callback_data="admin_channels")],
        [InlineKeyboardButton("📝 رسالة البدء", callback_data="admin_welcome")],
        [InlineKeyboardButton("👥 إعدادات المشرفين", callback_data="admin_admins")],
        [InlineKeyboardButton("💳 الدفع التلقائي", callback_data="admin_payment")],
        [InlineKeyboardButton("🛒 Shop (الاشتراكات)", callback_data="admin_shop")],
        [InlineKeyboardButton("🚪 خروج من الإدارة", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def subjects_keyboard():
    kb = [[InlineKeyboardButton(s, callback_data=f"subj_files:{s}")] for s in SUBJECTS]
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(kb)

def paginate_items(items, page, items_per_page=5):
    start = page * items_per_page
    end = start + items_per_page
    return items[start:end], len(items) > end

# ==============================================
# 4. معالجات المستخدم العامة
# ==============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_user(user.id)
    if not db_user:
        ref_code = context.args[0] if context.args else None
        referrer = None
        if ref_code:
            ref_user = db_query("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,), fetchone=True)
            if ref_user:
                referrer = ref_user[0]
                # تسجيل الإحالة
                db_query("INSERT INTO referrals (referrer_id, referred_id, referred_at) VALUES (?, ?, ?)",
                         (referrer, user.id, datetime.now().isoformat()), commit=True)
        create_user(user.id, user.username, user.first_name, user.last_name, referrer)
        if referrer:
            await update.message.reply_text("🎉 تم تفعيل كود الإحالة بنجاح! شكراً لك.")
    
    welcome = db_query("SELECT value FROM settings WHERE key = 'welcome_message'", fetchone=True)[0]
    await update.message.reply_text(welcome, reply_markup=main_menu_keyboard(user.id), parse_mode="Markdown")

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🌟 القائمة الرئيسية:", reply_markup=main_menu_keyboard(query.from_user.id))

async def show_subjects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📚 اختر المادة:", reply_markup=subjects_keyboard())

async def show_subject_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split(":", 1)[1]
    files = db_query("SELECT id, title, content_type, downloads FROM files WHERE subject = ? ORDER BY id DESC", (subject,), fetchall=True)
    if not files:
        await query.edit_message_text(f"لا يوجد ملفات لمادة {subject} حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="show_subjects")]]))
        return
    
    # Pagination (context)
    page = context.user_data.get(f"page_{subject}", 0)
    items_per_page = int(db_query("SELECT value FROM settings WHERE key = 'items_per_page'", fetchone=True)[0])
    paginated, has_next = paginate_items(files, page, items_per_page)
    
    kb = []
    for f in paginated:
        icon = "🎙️" if f[1] == "audio" else "📄" if f[1] == "document" else "🖼️"
        kb.append([InlineKeyboardButton(f"{icon} {f[0]}. {f[2]} ({f[3]} تحميل)", callback_data=f"get_file:{f[0]}")])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"subj_page:{subject}:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"subj_page:{subject}:{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 رجوع للمواد", callback_data="show_subjects")])
    await query.edit_message_text(f"📚 ملفات {subject}:", reply_markup=InlineKeyboardMarkup(kb))

async def subject_page_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, subject, page = query.data.split(":")
    context.user_data[f"page_{subject}"] = int(page)
    # Re-run the show subject files logic
    await show_subject_files(update, context)

async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_pk = int(query.data.split(":")[1])
    file = db_query("SELECT subject, content_type, title, file_id, file_name, description, requires_subscription FROM files WHERE id = ?", (file_pk,), fetchone=True)
    if not file:
        await query.message.reply_text("الملف غير موجود.")
        return
    
    user = get_user(query.from_user.id)
    # Check subscription if required
    if file[6] == 1 and user[8] == 'free':
        await query.message.reply_text("⛔ هذا الملف حصري للمشتركين المدفوعين. اشترك الآن من خلال لوحة الأدمن / Shop.")
        return
    
    # Log download
    db_query("INSERT INTO downloads_log (file_id, user_id, downloaded_at) VALUES (?, ?, ?)",
             (file_pk, query.from_user.id, datetime.now().isoformat()), commit=True)
    db_query("UPDATE files SET downloads = downloads + 1 WHERE id = ?", (file_pk,), commit=True)
    db_query("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (query.from_user.id,), commit=True)
    
    caption = f"📌 {file[2]}\n📚 {file[0]}\n📝 {file[5] or ' '}"
    if file[1] == "document":
        await query.message.reply_document(document=file[3], caption=caption)
    elif file[1] == "audio":
        await query.message.reply_audio(audio=file[3], caption=caption)
    elif file[1] == "video":
        await query.message.reply_video(video=file[3], caption=caption)
    elif file[1] == "photo":
        await query.message.reply_photo(photo=file[3], caption=caption)
    else:
        await query.message.reply_text("نوع ملف غير معروف.")

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("أنت غير مسجل، استخدم /start")
        return
    subs = SUBSCRIPTION_PLANS[user[8]]
    text = f"""
👤 *حسابي*
🆔 المعرف: {user[1]}
📛 الاسم: {user[3]} {user[4] or ''}
📅 تاريخ الانضمام: {user[5][:10]}
⭐ الاشتراك: *{subs['name']}*
📥 عدد التنزيلات: {user[10]}
🔗 كود الإحالة الخاص بك: `{user[7]}`
شارك الكود مع أصدقائك لكسب مكافآت!
    """
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

# ==============================================
# 5. نظام الإحالة (Referral)
# ==============================================
async def referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    if not user:
        return
    referrals = db_query("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (query.from_user.id,), fetchone=True)[0]
    text = f"""
⭐ *نظام الإحالة*
كودك الخاص: `{user[7]}`
شارك الرابط: `https://t.me/{context.bot.username}?start={user[7]}`

👥 عدد من سجلوا عن طريقك: {referrals}
🎁 لكل شخص يسجل عن طريقك، ستحصل أنت وهو على مكافأة!
(سيتم تفعيل المكافأة يدوياً أو تلقائياً حسب الإعدادات)
    """
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

# ==============================================
# 6. البحث
# ==============================================
async def search_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 أرسل الكلمة أو العلامة (Tag) التي تريد البحث عنها:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text
    files = db_query("SELECT id, subject, title, content_type FROM files WHERE title LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT 30",
                     (f"%{keyword}%", f"%{keyword}%"), fetchall=True)
    if not files:
        await update.message.reply_text("لا توجد نتائج.")
        return
    kb = []
    for f in files:
        icon = "🎙️" if f[3] == "audio" else "📄"
        kb.append([InlineKeyboardButton(f"{icon} {f[2]} ({f[1]})", callback_data=f"get_file:{f[0]}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await update.message.reply_text(f"🔍 نتائج '{keyword}':", reply_markup=InlineKeyboardMarkup(kb))

# ==============================================
# 7. رفع الملفات (محادثة متقدمة)
# ==============================================
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ غير مصرح.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(s, callback_data=f"upsubj:{s}")] for s in SUBJECTS]
    await update.message.reply_text("📤 رفع ملف جديد\nاختر المادة:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_SUBJECT

async def upload_subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["upload_subject"] = query.data.split(":")[1]
    await query.edit_message_text("اكتب عنوان الملف:")
    return ENTERING_TITLE

async def upload_title_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["upload_title"] = update.message.text
    await update.message.reply_text("اكتب وصفاً مختصراً (اختياري، أو اكتب 'تخطي'):")
    return ENTERING_DESC

async def upload_desc_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["upload_desc"] = None if text == "تخطي" else text
    await update.message.reply_text("اكتب علامات (Tags) مفصولة بفواصل (مثلاً: محاضرة, قلب, تشريح) أو اكتب 'تخطي':")
    return ENTERING_TAGS

async def upload_tags_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["upload_tags"] = None if text == "تخطي" else text
    await update.message.reply_text("هل تريد جعل هذا الملف حصرياً للمشتركين المدفوعين؟ (أرسل 'نعم' أو 'لا')")
    return RECEIVING_FILE

async def upload_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    # Check for subscription exclusive
    is_exclusive = 1 if msg.text and msg.text.lower() == 'نعم' else 0
    if msg.text and msg.text.lower() in ['نعم', 'لا']:
        # If they just replied with yes/no, we need to catch the file next. But we can handle it.
        # Actually, let's store it and wait for file.
        context.user_data["is_exclusive"] = is_exclusive
        await msg.reply_text("الآن أرسل الملف (PDF، صوت، فيديو، صورة):")
        return RECEIVING_FILE
    
    # Actual file receiving
    subject = context.user_data.get("upload_subject")
    title = context.user_data.get("upload_title")
    desc = context.user_data.get("upload_desc")
    tags = context.user_data.get("upload_tags")
    is_exclusive = context.user_data.get("is_exclusive", 0)
    
    if msg.document:
        content_type, file_id, file_name = "document", msg.document.file_id, msg.document.file_name
    elif msg.audio:
        content_type, file_id, file_name = "audio", msg.audio.file_id, msg.audio.file_name
    elif msg.voice:
        content_type, file_id, file_name = "audio", msg.voice.file_id, "voice.ogg"
    elif msg.video:
        content_type, file_id, file_name = "video", msg.video.file_id, msg.video.file_name
    elif msg.photo:
        content_type, file_id, file_name = "photo", msg.photo[-1].file_id, "photo.jpg"
    else:
        await msg.reply_text("أرسل ملفاً صالحاً.")
        return RECEIVING_FILE
    
    db_query("INSERT INTO files (subject, content_type, title, description, file_id, file_name, tags, uploaded_by, uploaded_at, requires_subscription) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
             (subject, content_type, title, desc, file_id, file_name, tags, update.effective_user.id, datetime.now().isoformat(), is_exclusive), commit=True)
    
    await msg.reply_text(f"✅ تم رفع الملف بنجاح!\nالمادة: {subject}\nالعنوان: {title}")
    context.user_data.clear()
    return ConversationHandler.END

async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END

# ==============================================
# 8. لوحة تحكم الأدمن المتكاملة (كل الأزرار)
# ==============================================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_qu
