#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Scheduler Bot - Professional Edition
Optimized for Render Free Tier
Author: Expert Developer
Version: 2.0.0
"""

import os
import re
import asyncio
import logging
import sqlite3
import json
from datetime import datetime, time, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from contextlib import contextmanager
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

@dataclass
class Config:
    """إعدادات البوت - تُحمل من متغيرات البيئة"""
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/bot.db")
    WEBHOOK_URL: str = os.getenv("RENDER_EXTERNAL_URL", "")  # Render يعطي هذا تلقائياً
    PORT: int = int(os.getenv("PORT", "10000"))
    TIMEZONE: str = "Asia/Riyadh"  # غير حسب منطقتك
    
    # Validate
    def validate(self) -> bool:
        return bool(self.BOT_TOKEN and self.ADMIN_ID and self.PORT)

CONFIG = Config()

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE LAYER (SQLite with Connection Pooling)
# ============================================================================

class Database:
    """طبقة قاعدة البيانات مع معالجة الأخطاء المتقدمة"""
    
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(exist_ok=True)
        self.init_tables()
    
    @contextmanager
    def connection(self):
        """Context manager للاتصالات مع إعادة المحاولة"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def init_tables(self):
        """إنشاء الجداول إذا لم تكن موجودة"""
        with self.connection() as conn:
            cursor = conn.cursor()
            
            # جدول العبارات
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS phrases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT UNIQUE,
                    file_name TEXT,
                    content TEXT NOT NULL,
                    total_count INTEGER DEFAULT 0,
                    current_index INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # جدول القنوات
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    channel_name TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول إعدادات الجدولة
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase_file_id TEXT,
                    posts_per_day INTEGER DEFAULT 3,
                    times TEXT,  -- JSON array ["09:00", "14:00", "20:00"]
                    start_date DATE,
                    end_date DATE,
                    is_active BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (phrase_file_id) REFERENCES phrases(file_id)
                )
            """)
            
            # جدول سجل النشر
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS publish_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase_id INTEGER,
                    channel_id TEXT,
                    content TEXT,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    error_msg TEXT
                )
            """)
            
            conn.commit()
            logger.info("Database tables initialized successfully")
    
    # --- Phrases Management ---
    
    def save_phrases(self, file_id: str, file_name: str, content: str) -> int:
        """حفظ ملف عبارات جديد"""
        phrases = self._parse_phrases(content)
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO phrases 
                (file_id, file_name, content, total_count, current_index, is_active)
                VALUES (?, ?, ?, ?, 0, 1)
            """, (file_id, file_name, json.dumps(phrases, ensure_ascii=False), len(phrases)))
            return len(phrases)
    
    def _parse_phrases(self, content: str) -> List[str]:
        """استخراج العبارات من النص بذكاء"""
        lines = content.strip().split('\n')
        phrases = []
        
        # أنماط الترقيم المدعومة: 1. | 1- | ١. | - | •
        patterns = [
            r'^\d+[\.\-\)]\s*(.+)',           # 1. أو 1- أو 1)
            r'^[\u0660-\u0669]+[\.\-\)]\s*(.+)', # الأرقام العربية ١.
            r'^[-•]\s*(.+)',                   # - أو •
            r'^\[\d+\]\s*(.+)',                # [1]
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            matched = False
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    phrases.append(match.group(1).strip())
                    matched = True
                    break
            
            # إذا لم يتطابق مع أي نمط، أضف السطر كاملاً (للمرونة)
            if not matched and len(line) > 3:
                phrases.append(line)
        
        return phrases
    
    def get_phrases(self, file_id: str) -> Optional[Dict]:
        """جلب ملف عبارات"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM phrases WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'file_id': row['file_id'],
                    'file_name': row['file_name'],
                    'phrases': json.loads(row['content']),
                    'total': row['total_count'],
                    'current': row['current_index'],
                    'is_active': bool(row['is_active'])
                }
            return None
    
    def get_next_phrase(self, file_id: str) -> Optional[str]:
        """جلب العبارة التالية وتحديث العداد"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content, current_index, total_count FROM phrases WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            
            if not row or row['current_index'] >= row['total_count']:
                return None
            
            phrases = json.loads(row['content'])
            next_phrase = phrases[row['current_index']]
            
            cursor.execute("""
                UPDATE phrases SET current_index = current_index + 1 
                WHERE file_id = ?
            """, (file_id,))
            
            return next_phrase
    
    def reset_phrases(self, file_id: str):
        """إعادة تعيين العداد للملف"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE phrases SET current_index = 0 WHERE file_id = ?", (file_id,))
    
    def delete_phrases(self, file_id: str):
        """حذف ملف عبارات"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM phrases WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM schedules WHERE phrase_file_id = ?", (file_id,))
    
    def list_phrases(self) -> List[Dict]:
        """قائمة جميع الملفات"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_id, file_name, total_count, current_index, is_active 
                FROM phrases ORDER BY created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    # --- Channels Management ---
    
    def add_channel(self, channel_id: str, channel_name: str = "") -> bool:
        """إضافة قناة"""
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO channels (channel_id, channel_name)
                    VALUES (?, ?)
                """, (channel_id, channel_name))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            return False
    
    def remove_channel(self, channel_id: str):
        """حذف قناة"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    
    def get_channels(self) -> List[Dict]:
        """جلب القنوات النشطة"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM channels WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
    
    # --- Schedule Management ---
    
    def set_schedule(self, file_id: str, posts_per_day: int, times: List[str]) -> int:
        """إعداد جدولة النشر"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO schedules 
                (phrase_file_id, posts_per_day, times, is_active)
                VALUES (?, ?, ?, 1)
            """, (file_id, posts_per_day, json.dumps(times)))
            return cursor.lastrowid
    
    def get_active_schedules(self) -> List[Dict]:
        """الجداول النشطة"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, p.file_name, p.current_index, p.total_count
                FROM schedules s
                JOIN phrases p ON s.phrase_file_id = p.file_id
                WHERE s.is_active = 1 AND p.is_active = 1
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def log_publish(self, phrase_id: int, channel_id: str, content: str, status: str, error: str = ""):
        """تسجيل عملية النشر"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO publish_log (phrase_id, channel_id, content, status, error_msg)
                VALUES (?, ?, ?, ?, ?)
            """, (phrase_id, channel_id, content[:500], status, error))

# ============================================================================
# SCHEDULER SERVICE
# ============================================================================

class PublishScheduler:
    """خدمة الجدولة المتقدمة مع APScheduler"""
    
    def __init__(self, bot, database: Database):
        self.bot = bot
        self.db = database
        self.scheduler = AsyncIOScheduler(timezone=CONFIG.TIMEZONE)
        self.scheduler.start()
        logger.info("Scheduler initialized")
    
    async def setup_schedule(self, file_id: str, posts_per_day: int, times: List[str]):
        """إعداد جدولة جديدة"""
        # إزالة المهام القديمة لهذا الملف
        self.remove_schedule(file_id)
        
        # حفظ في قاعدة البيانات
        schedule_id = self.db.set_schedule(file_id, posts_per_day, times)
        
        # إنشاء مهام cron
        for time_str in times:
            hour, minute = map(int, time_str.split(':'))
            
            job_id = f"publish_{file_id}_{time_str}"
            self.scheduler.add_job(
                self.publish_job,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=job_id,
                args=[file_id],
                replace_existing=True,
                misfire_grace_time=3600  # ساعة كحد أقصى للتأخير
            )
            logger.info(f"Scheduled job {job_id} at {time_str}")
        
        return schedule_id
    
    def remove_schedule(self, file_id: str):
        """إلغاء جدولة"""
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"publish_{file_id}"):
                job.remove()
                logger.info(f"Removed job {job.id}")
    
    async def publish_job(self, file_id: str):
        """مهمة النشر الفعلية"""
        try:
            # جلب العبارة التالية
            phrase = self.db.get_next_phrase(file_id)
            
            if not phrase:
                logger.info(f"No more phrases for file {file_id}")
                await self._notify_admin(f"✅ انتهت العبارات في الملف {file_id}")
                self.remove_schedule(file_id)
                return
            
            # جلب القنوات
            channels = self.db.get_channels()
            if not channels:
                logger.warning("No channels configured")
                return
            
            # النشر في كل القنوات
            success_count = 0
            for channel in channels:
                try:
                    await self.bot.send_message(
                        chat_id=channel['channel_id'],
                        text=phrase,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    success_count += 1
                    self.db.log_publish(0, channel['channel_id'], phrase, "success")
                    await asyncio.sleep(1)  # تجنب Rate Limit
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to publish to {channel['channel_id']}: {e}")
                    self.db.log_publish(0, channel['channel_id'], phrase, "failed", error_msg)
            
            logger.info(f"Published to {success_count}/{len(channels)} channels")
            
        except Exception as e:
            logger.error(f"Critical error in publish_job: {e}")
    
    async def _notify_admin(self, message: str):
        """إشعار المدير"""
        try:
            await self.bot.send_message(CONFIG.ADMIN_ID, message)
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
    
    def get_status(self) -> str:
        """حالة الجدولة"""
        jobs = self.scheduler.get_jobs()
        return f"Active jobs: {len(jobs)}"

# ============================================================================
# TELEGRAM HANDLERS
# ============================================================================

class BotHandlers:
    """معالجات أوامر التلجرام"""
    
    def __init__(self, db: Database, scheduler: PublishScheduler):
        self.db = db
        self.scheduler = scheduler
    
    def admin_only(func):
        """Decorator للتحقق من المدير"""
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return
            
            if update.effective_user.id != CONFIG.ADMIN_ID:
                await update.message.reply_text("⛔ Unauthorized access!")
                logger.warning(f"Unauthorized access attempt by {update.effective_user.id}")
                return
            
            return await func(self, update, context, *args, **kwargs)
        return wrapper
    
    @admin_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر البداية"""
        welcome_msg = """
🤖 <b>Bot Scheduler Pro</b>

مرحباً أيها المدير! الأوامر المتاحة:

📁 <b>إدارة الملفات:</b>
/upload - رفع ملف TXT
/list - قائمة الملفات
/delete - حذف ملف
/view - عرض محتوى ملف

📢 <b>إدارة القنوات:</b>
/addchannel - إضافة قناة
/channels - قائمة القنوات
/rmchannel - حذف قناة

⏰ <b>الجدولة:</b>
/schedule - إعداد جدولة نشر
/stop - إيقاف جدولة
/status - حالة النظام

📊 <b>معلومات:</ام

📊 <b>معلومات:</b>
/logs - سجل النشر
/help - المساعدة
        """
        await update.message.reply_html(welcome_msg)
    
    @admin_only
    async def upload_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة رفع الملف"""
        await update.message.reply_text(
            "📤 يرجى إرسال ملف TXT الآن.\n\n"
            "الصيغ المدعومة:\n"
            "• 1. نص العبارة\n"
            "• 1- نص العبارة\n"
            "• - نص العبارة\n"
            "• [1] نص العبارة"
        )
        context.user_data['awaiting_file'] = True
    
    @admin_only
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الملف المستلم"""
        if not context.user_data.get('awaiting_file'):
            return
        
        document = update.message.document
        
        # التحقق من النوع
        if not document.file_name.endswith('.txt'):
            await update.message.reply_text("❌ يجب أن يكون الملف بصيغة .txt")
            return
        
        # تحميل الملف
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{document.file_id}.txt"
        await file.download_to_drive(file_path)
        
        try:
            # قراءة المحتوى
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # حفظ في قاعدة البيانات
            count = self.db.save_phrases(document.file_id, document.file_name, content)
            
            await update.message.reply_text(
                f"✅ تم حفظ الملف بنجاح!\n\n"
                f"📄 الاسم: {document.file_name}\n"
                f"🔢 عدد العبارات: {count}\n"
                f"🆔 معرف الملف: <code>{document.file_id}</code>",
                parse_mode='HTML'
            )
            
            # عرض خيارات الجدولة
            keyboard = [
                [InlineKeyboardButton("⏰ جدولة النشر", callback_data=f"schedule:{document.file_id}")],
                [InlineKeyboardButton("👁 عرض العبارات", callback_data=f"view:{document.file_id}")],
                [InlineKeyboardButton("❌ حذف", callback_data=f"delete:{document.file_id}")]
            ]
            await update.message.reply_text(
                "ماذا تريد أن تفعل بهذا الملف؟",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            await update.message.reply_text(f"❌ خطأ في معالجة الملف: {str(e)}")
        finally:
            # تنظيف
            if os.path.exists(file_path):
                os.remove(file_path)
            context.user_data['awaiting_file'] = False
    
    @admin_only
    async def list_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قائمة الملفات"""
        files = self.db.list_phrases()
        
        if not files:
            await update.message.reply_text("📭 لا توجد ملفات محفوظة")
            return
        
        text = "📁 <b>الملفات المحفوظة:</b>\n\n"
        for f in files:
            progress = f"{f['current']}/{f['total']}"
            status = "🟢" if f['is_active'] else "🔴"
            text += f"{status} <code>{f['file_id'][:20]}...</code>\n"
            text += f"   📄 {f['file_name']}\n"
            text += f"   📊 {progress} عبارة\n\n"
        
        await update.message.reply_html(text)
    
    @admin_only
    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بدء إعداد الجدولة"""
        files = self.db.list_phrases()
        
        if not files:
            await update.message.reply_text("❌ لا توجد ملفات! استخدم /upload أولاً")
            return
        
        keyboard = []
        for f in files:
            if f['current'] < f['total']:  # لم ينتهِ بعد
                btn_text = f"📄 {f['file_name'][:20]} ({f['current']}/{f['total']})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"sched_select:{f['file_id']}")])
        
        await update.message.reply_text(
            "⏰ اختر الملف للجدولة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأزرار"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("sched_select:"):
            file_id = data.split(":")[1]
            context.user_data['scheduling_file'] = file_id
            
            # اختيار عدد المرات
            keyboard = [
                [InlineKeyboardButton("1 مرة يومياً", callback_data="posts:1")],
                [InlineKeyboardButton("2 مرات يومياً", callback_data="posts:2")],
                [InlineKeyboardButton("3 مرات يومياً", callback_data="posts:3")],
                [InlineKeyboardButton("4 مرات يومياً", callback_data="posts:4")],
                [InlineKeyboardButton("6 مرات يومياً", callback_data="posts:6")],
            ]
            await query.edit_message_text(
                "🔢 كم مرة تريد النشر في اليوم؟",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif data.startswith("posts:"):
            posts = int(data.split(":")[1])
            context.user_data['posts_per_day'] = posts
            
            # اختيار الأوقات
            suggestions = self._generate_time_suggestions(posts)
            keyboard = [[InlineKeyboardButton(t, callback_data=f"time:{t}")] for t in suggestions]
            keyboard.append([InlineKeyboardButton("⏰ أدخل يدوياً", callback_data="time:custom")])
            
            await query.edit_message_text(
                f"⏰ اختر توقيت النشر ({posts} مرات):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif data.startswith("time:"):
            time_choice = data.split(":")[1]
            
            if time_choice == "custom":
                await query.edit_message_text(
                    "⌨️ أرسل الأوقات بالتنسيق:\n"
                    "<code>09:00,14:00,20:00</code>",
                    parse_mode='HTML'
                )
                context.user_data['awaiting_times'] = True
            else:
                # تأكيد الجدولة
                await self._confirm_schedule(query, context, [time_choice])
        
        elif data == "confirm_schedule":
            # تنفيذ الجدولة
            file_id = context.user_data.get('scheduling_file')
            posts = context.user_data.get('posts_per_day', 1)
            times = context.user_data.get('selected_times', ['09:00'])
            
            await self.scheduler.setup_schedule(file_id, posts, times)
            
            times_str = ', '.join(times)
            await query.edit_message_text(
                f"✅ تم تفعيل الجدولة!\n\n"
                f"📄 الملف: <code>{file_id[:20]}...</code>\n"
                f"🔢 المرات: {posts} يومياً\n"
                f"⏰ الأوقات: {times_str}\n"
                f"📢 القنوات: {len(self.db.get_channels())}",
                parse_mode='HTML'
            )
    
    def _generate_time_suggestions(self, count: int) -> List[str]:
        """توليد اقتراحات أوقات منطقية"""
        if count == 1:
            return ["09:00", "12:00", "18:00", "20:00"]
        elif count == 2:
            return ["09:00,21:00", "10:00,18:00", "12:00,20:00"]
        elif count == 3:
            return ["09:00,14:00,20:00", "08:00,15:00,21:00"]
        elif count == 4:
            return ["09:00,12:00,15:00,18:00", "08:00,11:00,17:00,20:00"]
        else:
            return ["08:00,11:00,14:00,17:00,20:00,22:00"]
    
    async def _confirm_schedule(self, query, context, times):
        """عرض تأكيد الجدولة"""
        context.user_data['selected_times'] = times
        file_id = context.user_data.get('scheduling_file', '')[:20]
        
        keyboard = [[InlineKeyboardButton("✅ تأكيد", callback_data="confirm_schedule")]]
        await query.edit_message_text(
            f"📋 مراجعة الجدولة:\n\n"
            f"🆔 الملف: <code>{file_id}...</code>\n"
            f"⏰ الأوقات: {', '.join(times)}\n"
            f"📢 القنوات: {len(self.db.get_channels())}\n\n"
            f"هل تريد التأكيد؟",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    @admin_only
    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إضافة قناة"""
        await update.message.reply_text(
            "📢 لإضافة قناة:\n\n"
            "1. تأكد أن البوت مشرف في القناة\n"
            "2. أرسل معرف القناة\n\n"
            "الأمثلة:\n"
            "<code>@channelname</code>\n"
            "<code>-1001234567890</code>",
            parse_mode='HTML'
        )
        context.user_data['awaiting_channel'] = True
    
    @admin_only
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة النصوص العامة"""
        text = update.message.text
        
        # إضافة قناة
        if context.user_data.get('awaiting_channel'):
            channel_id = text.strip()
            
            # التحقق من صحة المعرف
            if not (channel_id.startswith('@') or channel_id.startswith('-100')):
                await update.message.reply_text("❌ معرف غير صالح. استخدم @channelname أو -100...")
                return
            
            success = self.db.add_channel(channel_id, channel_id)
            if success:
                await update.message.reply_text(f"✅ تمت إضافة القناة {channel_id}")
            else:
                await update.message.reply_text("⚠️ القناة موجودة مسبقاً أو خطأ في الإضافة")
            
            context.user_data['awaiting_channel'] = False
        
        # إدخال أوقات يدوي
        elif context.user_data.get('awaiting_times'):
            try:
                times = [t.strip() for t in text.split(',')]
                # التحقق من التنسيق
                for t in times:
                    datetime.strptime(t, '%H:%M')
                
                # الانتقال للتأكيد
                await self._confirm_schedule_manual(update, context, times)
                
            except ValueError:
                await update.message.reply_text("❌ تنسيق خاطئ. استخدم HH:MM مثل 09:00,14:00")
        
        else:
            await update.message.reply_text("❓ استخدم /help للأوامر المتاحة")
    
    async def _confirm_schedule_manual(self, update, context, times):
        """تأكيد يدوي"""
        context.user_data['selected_times'] = times
        context.user_data['awaiting_times'] = False
        file_id = context.user_data.get('scheduling_file', '')[:20]
        
        keyboard = [[InlineKeyboardButton("✅ تأكيد", callback_data="confirm_schedule")]]
        await update.message.reply_text(
            f"📋 مراجعة الجدولة:\n\n"
            f"🆔 الملف: <code>{file_id}...</code>\n"
            f"⏰ الأوقات: {', '.join(times)}\n"
            f"📢 القنوات: {len(self.db.get_channels())}\n\n"
            f"هل تريد التأكيد؟",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    @admin_only
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حالة النظام"""
        jobs_status = self.scheduler.get_status()
        channels = len(self.db.get_channels())
        files = len(self.db.list_phrases())
        
        status_text = f"""
📊 <b>حالة النظام</b>

⏰ الجدولة: {jobs_status}
📢 القنوات: {channels}
📁 الملفات: {files}
🤖 البوت: يعمل
⏱️ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        await update.message.reply_html(status_text)
    
    @admin_only
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """المساعدة"""
        help_text = """
📖 <b>دليل الاستخدام</b>

<b>1. رفع ملف:</b>
   /upload → أرسل ملف TXT

<b>2. إضافة قنوات:</b>
   /addchannel → أرسل @channel أو ID

<b>3. جدولة النشر:</b>
   /schedule → اختر الملف → حدد الأوقات

<b>4. المراقبة:</b>
   /status - حالة النظام
   /logs - سجل النشر
   /list - الملفات

<b>نصائح:</b>
• تأكد أن البوت مشرف في القنوات
• استخدم تنسيق TXT UTF-8
• الأوقات بتوقيت {CONFIG.TIMEZONE}
        """
        await update.message.reply_html(help_text)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

class TelegramSchedulerBot:
    """التطبيق الرئيسي"""
    
    def __init__(self):
        self.db = Database()
        self.scheduler = None
        self.handlers = None
    
    async def post_init(self, application: Application):
        """تهيئة ما بعد البدء"""
        self.scheduler = PublishScheduler(application.bot, self.db)
        self.handlers = BotHandlers(self.db, self.scheduler)
        
        # تسجيل المعالجات
        self._register_handlers(application)
        
        # إعداد الأوامر
        await self._setup_commands(application)
        
        logger.info("Bot initialized successfully")
    
    def _register_handlers(self, app: Application):
        """تسجيل المعالجات"""
        h = self.handlers
        
        # الأوامر
        app.add_handler(CommandHandler("start", h.start))
        app.add_handler(CommandHandler("help", h.help_command))
        app.add_handler(CommandHandler("upload", h.upload_file))
        app.add_handler(CommandHandler("list", h.list_files))
        app.add_handler(CommandHandler("schedule", h.schedule_command))
        app.add_handler(CommandHandler("addchannel", h.add_channel))
        app.add_handler(CommandHandler("status", h.status))
        
        # المعالجات العامة
        app.add_handler(MessageHandler(filters.Document.TXT, h.handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h.text_handler))
        app.add_handler(CallbackQueryHandler(h.callback_handler))
        
        # معالجة الأخطاء
        app.add_error_handler(self._error_handler)
    
    async def _setup_commands(self, app: Application):
        """إعداد قائمة الأوامر"""
        commands = [
            BotCommand("start", "بدء البوت"),
            BotCommand("upload", "رفع ملف TXT"),
            BotCommand("list", "قائمة الملفات"),
            BotCommand("schedule", "جدولة النشر"),
            BotCommand("addchannel", "إضافة قناة"),
            BotCommand("status", "حالة النظام"),
            BotCommand("help", "المساعدة"),
        ]
        await app.bot.set_my_commands(commands)
    
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء العام"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ! تحقق من السجلات."
            )
    
    def run(self):
        """تشغيل البوت"""
        if not CONFIG.validate():
            logger.error("Invalid configuration! Check BOT_TOKEN and ADMIN_ID")
            return
        
        application = Application.builder().token(CONFIG.BOT_TOKEN).build()
        
        # Webhook mode (موصى به لـ Render)
        if CONFIG.WEBHOOK_URL:
            webhook_path = f"/{CONFIG.BOT_TOKEN}"
            webhook_full = CONFIG.WEBHOOK_URL + webhook_path
            
            application.run_webhook(
                listen="0.0.0.0",
                port=CONFIG.PORT,
                webhook_url=webhook_full,
                secret_token=CONFIG.BOT_TOKEN.split(':')[1][:16]  # token secret
            )
        else:
            # Polling mode (للتطوير المحلي)
            application.run_polling(allowed_updates=Update.ALL_TYPES)

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    bot = TelegramSchedulerBot()
    bot.run()
