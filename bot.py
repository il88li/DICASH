import asyncio
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any
import pytz

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, Document, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

# ==================== إعدادات البوت ====================
TOKEN = "8476324781:AAFljvUAT6GYoysL_mvl8rCoADMNXcH1n1g"
ADMIN_ID = 6689435577  # معرف المدير المحدد
TIMEZONE = "Asia/Riyadh"  # المنطقة الزمنية (يمكن تغييرها)

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== قاعدة البيانات ====================
class Database:
    def __init__(self, db_path="bot.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # جدول العبارات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                file_id INTEGER,
                used INTEGER DEFAULT 0
            )
        """)
        # جدول الإعدادات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # جدول القنوات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                channel_name TEXT
            )
        """)
        # جدول الملفات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                file_name TEXT,
                uploaded_by INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def get_setting(self, key, default=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()

    def add_phrase(self, text, order_num, file_id=None):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO phrases (text, order_num, file_id) VALUES (?, ?, ?)",
            (text, order_num, file_id)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_next_phrase(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, text FROM phrases WHERE used=0 ORDER BY order_num LIMIT 1"
        )
        return cursor.fetchone()

    def mark_phrase_used(self, phrase_id):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE phrases SET used=1 WHERE id=?", (phrase_id,)
        )
        self.conn.commit()

    def get_remaining_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM phrases WHERE used=0")
        return cursor.fetchone()[0]

    def add_channel(self, channel_id, channel_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO channels (channel_id, channel_name) VALUES (?, ?)",
            (channel_id, channel_name)
        )
        self.conn.commit()

    def get_channels(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT channel_id, channel_name FROM channels")
        return cursor.fetchall()

    def add_file(self, file_id, file_name, uploaded_by):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO files (file_id, file_name, uploaded_by) VALUES (?, ?, ?)",
            (file_id, file_name, uploaded_by)
        )
        self.conn.commit()

    def get_files(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT file_id, file_name, uploaded_at FROM files")
        return cursor.fetchall()

    def delete_file(self, file_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files WHERE file_id=?", (file_id,))
        self.conn.commit()

    def reset_phrases(self):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE phrases SET used=0")
        self.conn.commit()

# تهيئة قاعدة البيانات
db = Database()

# ==================== إعداد البوت والجدولة ====================
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# جدولة المهام
jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.db')
}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=pytz.timezone(TIMEZONE))

# ==================== معالجة الأوامر ====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    await message.answer(
        "مرحباً يا مدير! 👨‍💼\n"
        "الأوامر المتاحة:\n"
        "/upload - رفع ملف نصي يحتوي على العبارات\n"
        "/set_channel - تعيين قناة للنشر\n"
        "/set_schedule - تعيين مواعيد النشر (مثل 08:00,12:00,18:00)\n"
        "/set_posts_per_day - تعيين عدد المنشورات اليومية\n"
        "/list_files - عرض الملفات المرفوعة\n"
        "/delete_file - حذف ملف\n"
        "/start_posting - بدء النشر المجدول\n"
        "/stop_posting - إيقاف النشر\n"
        "/status - عرض حالة النشر\n"
        "/reset - إعادة تعيين العبارات (تبدأ من الأول)"
    )

@dp.message(Command("upload"))
async def cmd_upload(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    await message.answer("أرسل ملف txt الذي يحتوي على العبارات المرقمة (مثال: 1. عبارة أولى)")

@dp.message(F.document & F.document.file_name.endswith('.txt'))
async def handle_txt_file(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    doc: Document = message.document
    if doc.file_size > 20 * 1024 * 1024:  # 20 ميغابايت حد أقصى
        await message.answer("حجم الملف كبير جداً. الحد الأقصى 20 ميغابايت.")
        return

    try:
        # تحميل الملف
        file = await bot.get_file(doc.file_id)
        file_path = file.file_path
        downloaded = await bot.download_file(file_path)
        content = downloaded.read().decode('utf-8')

        # تحليل العبارات المرقمة
        lines = content.strip().split('\n')
        pattern = r'^(\d+)\.\s*(.+)$'  مثل: 1. عبارة
        phrases_added = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(pattern, line)
            if match:
                order_num = int(match.group(1))
                text = match.group(2).strip()
                db.add_phrase(text, order_num, doc.file_id)
                phrases_added += 1
            else:
                # محاولة نمط آخر: 1) عبارة
                match = re.match(r'^(\d+)\)\s*(.+)$', line)
                if match:
                    order_num = int(match.group(1))
                    text = match.group(2).strip()
                    db.add_phrase(text, order_num, doc.file_id)
                    phrases_added += 1

        # حفظ الملف في قاعدة البيانات
        db.add_file(doc.file_id, doc.file_name, message.from_user.id)

        await message.answer(
            f"تم رفع الملف بنجاح!\n"
            f"عدد العبارات المضافة: {phrases_added}\n"
            f"الملف: {doc.file_name}"
        )
    except Exception as e:
        logger.error(f"خطأ في معالجة الملف: {e}")
        await message.answer(f"حدث خطأ أثناء معالجة الملف: {e}")

@dp.message(Command("set_channel"))
async def cmd_set_channel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    # توقع أن يكون الرسالة تحتوي على معرف القناة (مثل @channel_name)
    args = message.text.split()
    if len(args) < 2:
        await message.answer("استخدم: /set_channel @اسم_القناة")
        return
    channel = args[1]
    # يمكن إضافة تحقق من صحة القناة هنا
    db.add_channel(channel, channel)
    db.set_setting('current_channel', channel)
    await message.answer(f"تم تعيين القناة: {channel}")

@dp.message(Command("set_schedule"))
async def cmd_set_schedule(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("استخدم: /set_schedule 08:00,12:00,18:00")
        return
    times = args[1].split(',')
    # التحقق من صحة التواقيت
    valid_times = []
    for t in times:
        try:
            datetime.strptime(t, '%H:%M')
            valid_times.append(t)
        except ValueError:
            await message.answer(f"الوقت {t} غير صالح. استخدم صيغة HH:MM")
            return
    db.set_setting('schedule_times', ','.join(valid_times))
    await message.answer(f"تم تعيين مواعيد النشر: {', '.join(valid_times)}")

@dp.message(Command("set_posts_per_day"))
async def cmd_set_posts_per_day(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("استخدم: /set_posts_per_day <عدد>")
        return
    posts_per_day = int(args[1])
    db.set_setting('posts_per_day', str(posts_per_day))
    await message.answer(f"تم تعيين عدد المنشورات اليومية: {posts_per_day}")

@dp.message(Command("list_files"))
async def cmd_list_files(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    files = db.get_files()
    if not files:
        await message.answer("لا توجد ملفات مرفوعة.")
        return
    text = "الملفات المرفوعة:\n"
    for file_id, file_name, uploaded_at in files:
        text += f"• {file_name} (رفع: {uploaded_at})\n"
    await message.answer(text)

@dp.message(Command("delete_file"))
async def cmd_delete_file(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("استخدم: /delete_file <file_id>")
        return
    file_id = args[1]
    db.delete_file(file_id)
    await message.answer(f"تم حذف الملف {file_id}")

@dp.message(Command("start_posting"))
async def cmd_start_posting(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    # التحقق من وجود قناة وجدولة
    channel = db.get_setting('current_channel')
    if not channel:
        await message.answer("لم يتم تعيين قناة. استخدم /set_channel أولاً.")
        return
    schedule_times = db.get_setting('schedule_times')
    if not schedule_times:
        await message.answer("لم يتم تعيين مواعيد النشر. استخدم /set_schedule أولاً.")
        return
    # إعادة تعيين العبارات إذا كانت منتهية
    if db.get_remaining_count() == 0:
        db.reset_phrases()
        await message.answer("تم إعادة تعيين العبارات. ستبدأ من الأول.")
    # إضافة مهام الجدولة
    times = schedule_times.split(',')
    for t in times:
        hour, minute = map(int, t.split(':'))
        trigger = CronTrigger(hour=hour, minute=minute, timezone=pytz.timezone(TIMEZONE))
        scheduler.add_job(
            publish_phrase,
            trigger,
            id=f"publish_{t}",
            replace_existing=True,
            args=(channel,)
        )
    scheduler.start()
    await message.answer(f"بدأ النشر المجدول في القناة {channel} في الأوقات: {schedule_times}")

@dp.message(Command("stop_posting"))
async def cmd_stop_posting(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    scheduler.shutdown()
    await message.answer("تم إيقاف النشر المجدول.")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    channel = db.get_setting('current_channel', 'لم يتم تعيينه')
    schedule_times = db.get_setting('schedule_times', 'لم يتم تعيينه')
    posts_per_day = db.get_setting('posts_per_day', 'لم يتم تعيينه')
    remaining = db.get_remaining_count()
    total = db.conn.cursor().execute("SELECT COUNT(*) FROM phrases").fetchone()[0]
    status_text = (
        f"حالة النشر:\n"
        f"القناة: {channel}\n"
        f"مواعيد النشر: {schedule_times}\n"
        f"عدد المنشورات اليومية: {posts_per_day}\n"
        f"العبارات المتبقية: {remaining} من {total}\n"
        f"الجداولة نشطة: {scheduler.running}"
    )
    await message.answer(status_text)

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("أنت لست المدير المصرح به.")
        return
    db.reset_phrases()
    await message.answer("تم إعادة تعيين جميع العبارات (ستبدأ من الأول).")

# ==================== وظيفة النشر الأساسية ====================
async def publish_phrase(channel: str):
    try:
        phrase = db.get_next_phrase()
        if phrase is None:
            # لا توجد عبارات متبقية
            await bot.send_message(
                ADMIN_ID,
                "تم نشر جميع العبارات. النشر متوقف."
            )
            scheduler.shutdown()
            return
        phrase_id, text = phrase
        # إرسال العبارة إلى القناة
        await bot.send_message(channel, text)
        db.mark_phrase_used(phrase_id)
        remaining = db.get_remaining_count()
        if remaining == 0:
            await bot.send_message(
                ADMIN_ID,
                "تم نشر جميع العبارات. النشر متوقف."
            )
            scheduler.shutdown()
    except Exception as e:
        logger.error(f"خطأ أثناء النشر: {e}")
        await bot.send_message(
            ADMIN_ID,
            f"حدث خطأ أثناء النشر: {e}"
        )

# ==================== تشغيل البوت ====================
async def main():
    # استعادة المهام المجدولة من قاعدة البيانات (إذا كانت موجودة)
    if not scheduler.running:
        channel = db.get_setting('current_channel')
        schedule_times = db.get_setting('schedule_times')
        if channel and schedule_times:
            times = schedule_times.split(',')
            for t in times:
                hour, minute = map(int, t.split(':'))
                trigger = CronTrigger(hour=hour, minute=minute, timezone=pytz.timezone(TIMEZONE))
                scheduler.add_job(
                    publish_phrase,
                    trigger,
                    id=f"publish_{t}",
                    replace_existing=True,
                    args=(channel,)
                )
            scheduler.start()
            logger.info("تم استعادة الجداولة من قاعدة البيانات.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
