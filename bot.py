"""
PT SGU PDF Bot - @PhysicalTherapyDatabot
بوت لتخزين وتنظيم ملفات وريكوردات كلية العلاج الطبيعي - جامعة الصالحية الجديدة
"""

import os
import logging
import sqlite3
from datetime import datetime

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

# ============== الإعدادات ==============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_NEW_TOKEN_HERE")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]
DB_PATH = os.environ.get("DB_PATH", "pt_sgu.db")

# المواد المتاحة - عدّل القائمة دي براحتك
SUBJECTS = [
    "Anatomy",
    "Physiology",
    "Biophysics",
    "Biochemistry",
    "Kinesiology",
    "Manual Muscle Testing",
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# حالات المحادثة لرفع الملفات
CHOOSING_SUBJECT, CHOOSING_TYPE, ENTERING_TITLE, RECEIVING_FILE = range(4)

# ============== قاعدة البيانات ==============

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            content_type TEXT NOT NULL,
            title TEXT NOT NULL,
            file_id TEXT NOT NULL,
            file_name TEXT,
            uploaded_by INTEGER,
            uploaded_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_file(subject, content_type, title, file_id, file_name, uploaded_by):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO files (subject, content_type, title, file_id, file_name, uploaded_by, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (subject, content_type, title, file_id, file_name, uploaded_by, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_files_by_subject(subject):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, content_type, title, file_id, file_name FROM files WHERE subject = ? ORDER BY id DESC",
        (subject,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def search_files(keyword):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, subject, content_type, title, file_id, file_name FROM files "
        "WHERE title LIKE ? OR file_name LIKE ? ORDER BY id DESC LIMIT 20",
        (f"%{keyword}%", f"%{keyword}%"),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_file_by_id(file_pk):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT subject, content_type, title, file_id, file_name FROM files WHERE id = ?", (file_pk,))
    row = cur.fetchone()
    conn.close()
    return row


def delete_file(file_pk):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM files WHERE id = ?", (file_pk,))
    conn.commit()
    conn.close()


def is_admin(user_id):
    return user_id in ADMIN_IDS


# ============== أوامر عامة ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 أهلاً بيك في بوت *PT SGU PDF*\n\n"
        "هنا تقدر تلاقي وتطلب ملفات، ملخصات، وريكوردات المحاضرات لكل مواد الفرقة.\n\n"
        "📚 /materials - عرض المواد\n"
        "🔍 /search كلمة - البحث عن ملف\n"
        "📤 /upload - رفع ملف (للأدمن بس)\n"
        "ℹ️ /help - المساعدة"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(subj, callback_data=f"subj:{subj}")] for subj in SUBJECTS
    ]
    await update.message.reply_text(
        "📚 اختار المادة اللي عايزها:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split(":", 1)[1]
    rows = get_files_by_subject(subject)

    if not rows:
        await query.edit_message_text(f"لا يوجد ملفات لمادة {subject} لسه 🙁")
        return

    keyboard = []
    for row in rows:
        file_pk, content_type, title, _, _ = row
        icon = "🎙️" if content_type == "audio" else "📄"
        keyboard.append([InlineKeyboardButton(f"{icon} {title}", callback_data=f"get:{file_pk}")])

    await query.edit_message_text(
        f"📚 ملفات {subject}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_pk = int(query.data.split(":", 1)[1])
    row = get_file_by_id(file_pk)

    if not row:
        await query.message.reply_text("الملف ده مش موجود (ممكن يكون اتمسح).")
        return

    subject, content_type, title, file_id, file_name = row
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


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استخدم كذا: /search اسم الملف أو كلمة من العنوان")
        return

    keyword = " ".join(context.args)
    rows = search_files(keyword)

    if not rows:
        await update.message.reply_text("مفيش نتائج 🙁")
        return

    keyboard = []
    for row in rows:
        file_pk, subject, content_type, title, _, _ = row
        icon = "🎙️" if content_type == "audio" else "📄"
        keyboard.append([InlineKeyboardButton(f"{icon} {title} ({subject})", callback_data=f"get:{file_pk}")])

    await update.message.reply_text(
        f"🔍 نتائج البحث عن '{keyword}':",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============== رفع الملفات (أدمن فقط) ==============

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ الأمر ده للأدمن بس.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(subj, callback_data=f"upsubj:{subj}")] for subj in SUBJECTS
    ]
    await update.message.reply_text(
        "📤 اختار المادة اللي هترفع لها الملف:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSING_SUBJECT


async def upload_subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split(":", 1)[1]
    context.user_data["upload_subject"] = subject
    await query.edit_message_text(f"تمام، المادة: {subject}\nدلوقتي اكتب عنوان الملف (مثلاً: محاضرة 3 - القلب):")
    return ENTERING_TITLE


async def upload_title_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["upload_title"] = update.message.text
    await update.message.reply_text("تمام 👌 دلوقتي بعت الملف (PDF / صورة / صوت / فيديو):")
    return RECEIVING_FILE


async def upload_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    subject = context.user_data.get("upload_subject")
    title = context.user_data.get("upload_title")

    if msg.document:
        content_type = "document"
        file_id = msg.document.file_id
        file_name = msg.document.file_name
    elif msg.audio:
        content_type = "audio"
        file_id = msg.audio.file_id
        file_name = msg.audio.file_name
    elif msg.voice:
        content_type = "audio"
        file_id = msg.voice.file_id
        file_name = "voice_note.ogg"
    elif msg.video:
        content_type = "video"
        file_id = msg.video.file_id
        file_name = msg.video.file_name
    elif msg.photo:
        content_type = "photo"
        file_id = msg.photo[-1].file_id
        file_name = "photo.jpg"
    else:
        await msg.reply_text("الرجاء إرسال ملف (PDF / صوت / فيديو / صورة).")
        return RECEIVING_FILE

    add_file(subject, content_type, title, file_id, file_name, update.effective_user.id)
    await msg.reply_text(f"✅ تم الحفظ بنجاح!\n📚 المادة: {subject}\n📌 العنوان: {title}")
    context.user_data.clear()
    return ConversationHandler.END


async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ الأمر ده للأدمن بس.")
        return
    if not context.args:
        await update.message.reply_text("استخدم كذا: /delete رقم_الملف (هتعرفه من /search)")
        return
    try:
        file_pk = int(context.args[0])
    except ValueError:
        await update.message.reply_text("رقم غير صحيح.")
        return
    delete_file(file_pk)
    await update.message.reply_text("🗑️ تم الحذف (لو كان موجود).")


# ============== main ==============

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("materials", materials))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))

    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_start)],
        states={
            CHOOSING_SUBJECT: [CallbackQueryHandler(upload_subject_chosen, pattern=r"^upsubj:")],
            ENTERING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_title_entered)],
            RECEIVING_FILE: [MessageHandler(
                filters.Document.ALL | filters.AUDIO | filters.VOICE | filters.VIDEO | filters.PHOTO,
                upload_file_received,
            )],
        },
        fallbacks=[CommandHandler("cancel", upload_cancel)],
    )
    app.add_handler(upload_conv)

    app.add_handler(CallbackQueryHandler(subject_chosen, pattern=r"^subj:"))
    app.add_handler(CallbackQueryHandler(send_file, pattern=r"^get:"))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
    
