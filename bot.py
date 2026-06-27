"""
PT SGU PDF Bot - النسخة الاحترافية المتطورة
كلية العلاج الطبيعي - جامعة الصالحية الجديدة
"""

import os
import logging
import sqlite3
from datetime import datetime
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ================== التوكن والآيدي ==================
BOT_TOKEN = "8962028467:AAHNlT1yiDM9ShCEUVL3ebZJ0MBQVukFmm8"
ADMIN_IDS = [8704784390]  # ضع معرفات الأدمن هنا (أكثر من واحد بالفاصلة)
DB_PATH = "pt_sgu_pro.db"

# المواد الدراسية (عدل براحتك)
SUBJECTS = [
    "Anatomy", "Physiology", "Biophysics", "Biochemistry",
    "Kinesiology", "Manual Muscle Testing", "Neuroanatomy",
    "Pathology", "Pharmacology"
]

# ================== إعدادات التسجيل ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================== حالات المحادثة ==================
CHOOSING_SUBJECT, ENTERING_TITLE, RECEIVING_FILE = range(3)
AWAITING_ANNOUNCEMENT = 10

# ================== قاعدة البيانات ==================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # جدول الملفات (نفس القديم)
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        content_type TEXT NOT NULL,
        title TEXT NOT NULL,
        file_id TEXT NOT NULL,
        file_name TEXT,
        uploaded_by INTEGER,
        uploaded_at TEXT,
        downloads INTEGER DEFAULT 0
    )""")
    # جدول المستخدمين (جديد)
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at TEXT,
        is_admin INTEGER DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by INTEGER
    )""")
    # جدول الإعدادات
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    # جدول الإعلانات
    c.execute("""CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        created_at TEXT
    )""")
    # إعدادات افتراضية
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_message', 'مرحباً بك في بوت PT SGU!\\nاختر من القائمة أدناه.')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('items_per_page', '5')")
    conn.commit()
    conn.close()

# دوال مساعدة للـ DB
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

def get_user(user_id):
    return db_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)

def create_user(user_id, username, first_name, referred_by=None):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return db_query(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, referral_code, referred_by) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, first_name, datetime.now().isoformat(), code, referred_by),
        commit=True
    )

def is_admin(user_id):
    return user_id in ADMIN_IDS

def add_file(subject, content_type, title, file_id, file_name, uploaded_by):
    db_query(
        "INSERT INTO files (subject, content_type, title, file_id, file_name, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (subject, content_type, title, file_id, file_name, uploaded_by, datetime.now().isoformat()),
        commit=True
    )

def get_files_by_subject(subject):
    return db_query("SELECT id, content_type, title, file_id, file_name FROM files WHERE subject = ? ORDER BY id DESC", (subject,), fetchall=True)

def search_files(keyword):
    return db_query(
        "SELECT id, subject, content_type, title, file_id, file_name FROM files WHERE title LIKE ? OR file_name LIKE ? ORDER BY id DESC LIMIT 20",
        (f"%{keyword}%", f"%{keyword}%"), fetchall=True
    )

def get_file_by_id(file_pk):
    return db_query("SELECT subject, content_type, title, file_id, file_name FROM files WHERE id = ?", (file_pk,), fetchone=True)

def delete_file(file_pk):
    db_query("DELETE FROM files WHERE id = ?", (file_pk,), commit=True)

def get_stats():
    users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    files = db_query("SELECT COUNT(*) FROM files", fetchone=True)[0]
    downloads = db_query("SELECT SUM(downloads) FROM files", fetchone=True)[0] or 0
    return users, files, downloads

# ================== لوحات المفاتيح ==================
def main_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📚 المواد الدراسية", callback_data="show_subjects")],
        [InlineKeyboardButton("🔍 بحث", callback_data="search_menu")],
        [InlineKeyboardButton("👤 حسابي", callback_data="my_profile")],
        [InlineKeyboardButton("⭐ نظام الإحالة", callback_data="referral_menu")],
        [InlineKeyboardButton("📢 الإعلانات", callback_data="show_announcements")],
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 إدارة الملفات", callback_data="admin_files")],
        [InlineKeyboardButton("📢 إرسال إعلان", callback_data="admin_announce")],
        [InlineKeyboardButton("🔧 الإعدادات", callback_data="admin_settings")],
        [InlineKeyboardButton("📝 رسالة البدء", callback_data="admin_welcome")],
        [InlineKeyboardButton("👥 إدارة المشرفين", callback_data="admin_admins")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def subjects_keyboard():
    kb = [[InlineKeyboardButton(s, callback_data=f"subj_files:{s}")] for s in SUBJECTS]
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(kb)

# ================== أوامر المستخدم ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # تسجيل المستخدم
    if not get_user(user.id):
        ref_code = context.args[0] if context.args else None
        referrer = None
        if ref_code:
            ref_user = db_query("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,), fetchone=True)
            if ref_user:
                referrer = ref_user[0]
        create_user(user.id, user.username, user.first_name, referrer)
        if referrer:
            await update.message.reply_text("🎉 تم تفعيل كود الإحالة!")
    
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
    rows = get_files_by_subject(subject)
    if not rows:
        await query.edit_message_text(f"لا يوجد ملفات لمادة {subject}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="show_subjects")]]))
        return
    kb = []
    for row in rows:
        file_pk, content_type, title, _, _ = row
        icon = "🎙️" if content_type == "audio" else "📄" if content_type == "document" else "🖼️"
        kb.append([InlineKeyboardButton(f"{icon} {title}", callback_data=f"get_file:{file_pk}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="show_subjects")])
    await query.edit_message_text(f"📚 ملفات {subject}:", reply_markup=InlineKeyboardMarkup(kb))

async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_pk = int(query.data.split(":")[1])
    row = get_file_by_id(file_pk)
    if not row:
        await query.message.reply_text("الملف غير موجود.")
        return
    subject, content_type, title, file_id, file_name = row
    # تحديث عدد التحميلات
    db_query("UPDATE files SET downloads = downloads + 1 WHERE id = ?", (file_pk,), commit=True)
    caption = f"📌 {title}\n📚 {subject}"
    if content_type == "document":
        await query.message.reply_document(document=file_id, caption=caption)
    elif content_type == "audio":
        await query.message.reply_audio(audio=file_id, caption=caption)
    elif content_type == "video":
        await query.message.reply_video(video=file_id, caption=caption)
    elif content_type == "photo":
        await query.message.reply_photo(photo=file_id, caption=caption)
    else:
        await query.message.reply_text("نوع ملف غير معروف.")

async def search_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 أرسل الكلمة التي تريد البحث عنها:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text
    rows = search_files(keyword)
    if not rows:
        await update.message.reply_text("لا توجد نتائج.")
        return
    kb = []
    for row in rows:
        file_pk, subject, content_type, title, _, _ = row
        icon = "🎙️" if content_type == "audio" else "📄"
        kb.append([InlineKeyboardButton(f"{icon} {title} ({subject})", callback_data=f"get_file:{file_pk}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await update.message.reply_text(f"🔍 نتائج '{keyword}':", reply_markup=InlineKeyboardMarkup(kb))

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("أنت غير مسجل، استخدم /start")
        return
    text = f"""
👤 *حسابي*
🆔 المعرف: {user[0]}
📛 الاسم: {user[2]}
📅 تاريخ الانضمام: {user[3][:10]}
🔗 كود الإحالة: `{user[5]}`
شارك الرابط: `https://t.me/{context.bot.username}?start={user[5]}`
    """
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("أنت غير مسجل.")
        return
    text = f"""
⭐ *نظام الإحالة*
كودك: `{user[5]}`
رابط الدعوة: `https://t.me/{context.bot.username}?start={user[5]}`

شارك الرابط مع أصدقائك، وعندما يسجلون عن طريقك ستحصل أنت وهم على مكافآت!
    """
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def show_announcements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db_query("SELECT text, created_at FROM announcements ORDER BY id DESC LIMIT 5", fetchall=True)
    if not rows:
        await query.edit_message_text("لا توجد إعلانات حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))
        return
    text = "📢 *آخر الإعلانات*\n\n"
    for t, d in rows:
        text += f"📅 {d[:10]}\n{t}\n\n"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

# ================== رفع الملفات (أدمن) ==================
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ للأدمن فقط.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(s, callback_data=f"upsubj:{s}")] for s in SUBJECTS]
    await update.message.reply_text("📤 اختر المادة:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_SUBJECT

async def upload_subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["upload_subject"] = query.data.split(":")[1]
    await query.edit_message_text("اكتب عنوان الملف:")
    return ENTERING_TITLE

async def upload_title_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["upload_title"] = update.message.text
    await update.message.reply_text("أرسل الملف الآن (PDF، صوت، فيديو، صورة):")
    return RECEIVING_FILE

async def upload_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    subject = context.user_data.get("upload_subject")
    title = context.user_data.get("upload_title")
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
    add_file(subject, content_type, title, file_id, file_name, update.effective_user.id)
    await msg.reply_text(f"✅ تم الحفظ!\nالمادة: {subject}\nالعنوان: {title}")
    context.user_data.clear()
    return ConversationHandler.END

async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END

# ================== لوحة الأدمن ==================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ غير مصرح.")
        return
    await query.edit_message_text("👑 لوحة التحكم:", reply_markup=admin_panel_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users, files, downloads = get_stats()
    text = f"""
📊 *الإحصائيات*
👥 المستخدمين: {users}
📁 الملفات: {files}
📥 إجمالي التحميلات: {downloads}
    """
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))

async def admin_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db_query("SELECT id, title, subject FROM files ORDER BY id DESC LIMIT 20", fetchall=True)
    if not rows:
        await query.edit_message_text("لا توجد ملفات.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))
        return
    kb = []
    for f in rows:
        kb.append([InlineKeyboardButton(f"🗑️ {f[1]} ({f[2]})", callback_data=f"del_file:{f[0]}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    await query.edit_message_text("📁 آخر 20 ملف (اضغط للحذف):", reply_markup=InlineKeyboardMarkup(kb))

async def delete_file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_pk = int(query.data.split(":")[1])
    delete_file(file_pk)
    await query.edit_message_text("🗑️ تم الحذف.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_files")]]))

async def admin_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 أرسل نص الإعلان:")
    return AWAITING_ANNOUNCEMENT

async def send_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    # حفظ الإعلان في قاعدة البيانات
    db_query("INSERT INTO announcements (text, created_at) VALUES (?, ?)", (text, datetime.now().isoformat()), commit=True)
    # إرسال لكل المستخدمين
    users = db_query("SELECT user_id FROM users", fetchall=True)
    count = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=f"📢 *إعلان جديد*\n\n{text}", parse_mode="Markdown")
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ تم إرسال الإعلان إلى {count} مستخدم.")
    return ConversationHandler.END

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    items = db_query("SELECT value FROM settings WHERE key = 'items_per_page'", fetchone=True)[0]
    text = f"🔧 الإعدادات:\nعدد الملفات في الصفحة: {items}"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))

async def admin_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 أرسل نص رسالة البدء الجديدة (Markdown مدعوم):")
    # سنستخدم نفس حالة الإعلان مؤقتاً، لكننا سنضيف معالجاً جديداً
    # لكن للتبسيط، سنستخدم نفس ConversationHandler للإعلان مع متغير
    context.user_data["edit_welcome"] = True
    return AWAITING_ANNOUNCEMENT

async def save_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("edit_welcome"):
        text = update.message.text
        db_query("UPDATE settings SET value = ? WHERE key = 'welcome_message'", (text,), commit=True)
        await update.message.reply_text("✅ تم تحديث رسالة البدء.")
        context.user_data.clear()
        return ConversationHandler.END
    else:
        # إذا كان إعلاناً عادياً، يمر للدالة السابقة
        return await send_announcement(update, context)

async def admin_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admins = db_query("SELECT user_id, username, first_name FROM users WHERE user_id IN ({})".format(','.join(map(str, ADMIN_IDS))), fetchall=True)
    txt = "👥 المشرفون الحاليون:\n"
    for a in admins:
        txt += f"• {a[2]} (@{a[1] or 'غير معروف'}) - {a[0]}\n"
    txt += "\nلإضافة أو حذف مشرف، عدل قائمة ADMIN_IDS في الكود وأعد تشغيل البوت."
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))

# ================== التشغيل الرئيسي ==================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر المستخدم
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", upload_start))  # رفع ملفات

    # معالجات الكول باك
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(show_subjects, pattern="^show_subjects$"))
    app.add_handler(CallbackQueryHandler(show_subject_files, pattern="^subj_files:"))
    app.add_handler(CallbackQueryHandler(get_file, pattern="^get_file:"))
    app.add_handler(CallbackQueryHandler(search_menu, pattern="^search_menu$"))
    app.add_handler(CallbackQueryHandler(my_profile, pattern="^my_profile$"))
    app.add_handler(CallbackQueryHandler(referral_menu, pattern="^referral_menu$"))
    app.add_handler(CallbackQueryHandler(show_announcements, pattern="^show_announcements$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_files, pattern="^admin_files$"))
    app.add_handler(CallbackQueryHandler(delete_file_cmd, pattern="^del_file:"))
    app.add_handler(CallbackQueryHandler(admin_announce, pattern="^admin_announce$"))
    app.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(admin_welcome, pattern="^admin_welcome$"))
    app.add_handler(CallbackQueryHandler(admin_admins, pattern="^admin_admins$"))

    # محادثة رفع الملفات
    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_start)],
        states={
            CHOOSING_SUBJECT: [CallbackQueryHandler(upload_subject_chosen, pattern=r"^upsubj:")],
            ENTERING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_title_entered)],
            RECEIVING_FILE: [MessageHandler(filters.Document.ALL | filters.AUDIO | filters.VOICE | filters.VIDEO | filters.PHOTO, upload_file_received)],
        },
        fallbacks=[CommandHandler("cancel", upload_cancel)],
    )
    app.add_handler(upload_conv)

    # محادثة للإعلانات وتعديل رسالة البدء (نفس الحالة)
    announce_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_announce, pattern="^admin_announce$"), CallbackQueryHandler(admin_welcome, pattern="^admin_welcome$")],
        states={
            AWAITING_ANNOUNCEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_welcome)],
        },
        fallbacks=[CommandHandler("cancel", upload_cancel)],
    )
    app.add_handler(announce_conv)

    # معالجة البحث النصي
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))

    logger.info("🚀 البوت شغال الآن!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
