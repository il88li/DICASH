#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Scheduler Bot - Render Optimized Edition
Fixed post_init issue
Version: 3.1.0
"""

import os
import re
import asyncio
import logging
import sqlite3
import json
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
from functools import wraps
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ExtBot
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    PORT: int = int(os.getenv("PORT", "10000"))
    RENDER_EXTERNAL_URL: str = os.getenv("RENDER_EXTERNAL_URL", "")
    TIMEZONE: str = os.getenv("TZ", "Asia/Riyadh")
    
    @property
    def WEBHOOK_URL(self) -> str:
        if self.RENDER_EXTERNAL_URL:
            base = self.RENDER_EXTERNAL_URL.rstrip('/')
            return f"{base}/webhook"
        return ""
    
    @property
    def WEBHOOK_SECRET(self) -> str:
        return self.BOT_TOKEN.split(':')[1] if ':' in self.BOT_TOKEN else "default_secret"
    
    def validate(self) -> bool:
        if not self.BOT_TOKEN or self.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            logging.error("❌ BOT_TOKEN غير مضبوط!")
            return False
        if not self.ADMIN_ID or self.ADMIN_ID == 0:
            logging.error("❌ ADMIN_ID غير مضبوط!")
            return False
        return True

CONFIG = Config()

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# KEEP-ALIVE SERVER
# ============================================================================

class KeepAliveHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {
            "status": "alive",
            "bot": "running",
            "timestamp": datetime.now().isoformat(),
            "service": "telegram-scheduler-bot"
        }
        self.wfile.write(json.dumps(response).encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_keep_alive_server(port: int = 8080):
    def run_server():
        try:
            server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
            logger.info(f"🌐 Keep-Alive Server على المنفذ {port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"❌ خطأ Keep-Alive: {e}")
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread

# ============================================================================
# SELF-PING SYSTEM
# ============================================================================

class SelfPing:
    def __init__(self, url: str, interval: int = 600):
        self.url = url
        self.interval = interval
        self.running = False
    
    def start(self):
        if not self.url or self.running:
            return
        
        self.running = True
        
        def ping_loop():
            import urllib.request
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            while self.running:
                try:
                    req = urllib.request.Request(
                        self.url,
                        headers={'User-Agent': 'TelegramBot-KeepAlive/1.0'},
                        method='HEAD'
                    )
                    with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                        logger.info(f"💓 Self-Ping: {resp.status}")
                except Exception as e:
                    logger.warning(f"⚠️ Self-Ping: {e}")
                time.sleep(self.interval)
        
        thread = threading.Thread(target=ping_loop, daemon=True)
        thread.start()
        logger.info(f"🔄 Self-Ping: {self.url}")

# ============================================================================
# DATABASE
# ============================================================================

class Database:
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(exist_ok=True)
        self.init_tables()
    
    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_tables(self):
        with self.connection() as conn:
            cursor = conn.cursor()
            
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
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    channel_name TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase_file_id TEXT,
                    posts_per_day INTEGER DEFAULT 3,
                    times TEXT,
                    is_active BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (phrase_file_id) REFERENCES phrases(file_id)
                )
            """)
            
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

    def save_phrases(self, file_id: str, file_name: str, content: str) -> int:
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
        lines = content.strip().split('\n')
        phrases = []
        patterns = [
            r'^\d+[\.\-\)]\s*(.+)',
            r'^[\u0660-\u0669]+[\.\-\)]\s*(.+)',
            r'^[-•]\s*(.+)',
            r'^\[\d+\]\s*(.+)',
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
            
            if not matched and len(line) > 3:
                phrases.append(line)
        
        return phrases
    
    def get_next_phrase(self, file_id: str) -> Optional[str]:
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
    
    def add_channel(self, channel_id: str, channel_name: str = "") -> bool:
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO channels (channel_id, channel_name)
                    VALUES (?, ?)
                """, (channel_id, channel_name))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error: {e}")
            return False
    
    def get_channels(self) -> List[Dict]:
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM channels WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
    
    def list_phrases(self) -> List[Dict]:
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_id, file_name, total_count, current_index, is_active 
                FROM phrases ORDER BY created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def set_schedule(self, file_id: str, posts_per_day: int, times: List[str]) -> int:
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO schedules 
                (phrase_file_id, posts_per_day, times, is_active)
                VALUES (?, ?, ?, 1)
            """, (file_id, posts_per_day, json.dumps(times)))
            return cursor.lastrowid

# ============================================================================
# SCHEDULER
# ============================================================================

class PublishScheduler:
    def __init__(self, bot, database: Database):
        self.bot = bot
        self.db = database
        self.scheduler = AsyncIOScheduler(timezone=CONFIG.TIMEZONE)
        self.scheduler.start()
        logger.info("✅ Scheduler initialized")
    
    async def setup_schedule(self, file_id: str, posts_per_day: int, times: List[str]):
        self.remove_schedule(file_id)
        self.db.set_schedule(file_id, posts_per_day, times)
        
        for time_str in times:
            hour, minute = map(int, time_str.split(':'))
            job_id = f"publish_{file_id}_{time_str}"
            self.scheduler.add_job(
                self.publish_job,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=job_id,
                args=[file_id],
                replace_existing=True,
                misfire_grace_time=3600
            )
            logger.info(f"⏰ Scheduled: {job_id} at {time_str}")
    
    def remove_schedule(self, file_id: str):
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"publish_{file_id}"):
                job.remove()
    
    async def publish_job(self, file_id: str):
        try:
            phrase = self.db.get_next_phrase(file_id)
            
            if not phrase:
                logger.info(f"✅ Finished: {file_id}")
                await self._notify_admin("✅ انتهت العبارات!")
                self.remove_schedule(file_id)
                return
            
            channels = self.db.get_channels()
            if not channels:
                logger.warning("⚠️ No channels")
                return
            
            for channel in channels:
                try:
                    await self.bot.send_message(
                        chat_id=channel['channel_id'],
                        text=phrase,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"❌ Failed: {channel['channel_id']}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Critical: {e}")
    
    async def _notify_admin(self, message: str):
        try:
            await self.bot.send_message(CONFIG.ADMIN_ID, message)
        except Exception as e:
            logger.error(f"Failed notify: {e}")

# ============================================================================
# HANDLERS
# ============================================================================

class BotHandlers:
    def __init__(self, db: Database, scheduler: PublishScheduler):
        self.db = db
        self.scheduler = scheduler
    
    def admin_only(func):
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return
            if update.effective_user.id != CONFIG.ADMIN_ID:
                await update.message.reply_text("⛔ Unauthorized!")
                return
            return await func(self, update, context, *args, **kwargs)
        return wrapper
    
    @admin_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_html("""
🤖 <b>Bot Scheduler Pro</b>

📁 /upload - رفع TXT
📋 /list - الملفات
⏰ /schedule - جدولة
📢 /addchannel - قناة
📊 /status - الحالة
❓ /help - مساعدة
        """)
    
    @admin_only
    async def upload_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📤 أرسل ملف TXT")
        context.user_data['awaiting_file'] = True
    
    @admin_only
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get('awaiting_file'):
            return
        
        document = update.message.document
        
        if not document.file_name.endswith('.txt'):
            await update.message.reply_text("❌ يجب أن يكون .txt")
            return
        
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{document.file_id}.txt"
        await file.download_to_drive(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            count = self.db.save_phrases(document.file_id, document.file_name, content)
            
            await update.message.reply_text(
                f"✅ تم الحفظ!\n\n"
                f"📄 {document.file_name}\n"
                f"🔢 {count} عبارة",
                parse_mode='HTML'
            )
            
            keyboard = [[InlineKeyboardButton("⏰ جدولة", callback_data=f"schedule:{document.file_id}")]]
            await update.message.reply_text("ماذا تفعل؟", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
            context.user_data['awaiting_file'] = False
    
    @admin_only
    async def list_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        files = self.db.list_phrases()
        
        if not files:
            await update.message.reply_text("📭 لا توجد ملفات")
            return
        
        text = "📁 <b>الملفات:</b>\n\n"
        for f in files:
            progress = f"{f['current']}/{f['total']}"
            status = "🟢" if f['is_active'] else "🔴"
            text += f"{status} {f['file_name'][:20]}... ({progress})\n"
        
        await update.message.reply_html(text)
    
    @admin_only
    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        files = self.db.list_phrases()
        
        if not files:
            await update.message.reply_text("❌ لا توجد ملفات!")
            return
        
        keyboard = []
        for f in files:
            if f['current'] < f['total']:
                btn_text = f"📄 {f['file_name'][:20]} ({f['current']}/{f['total']})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"sched_select:{f['file_id']}")])
        
        await update.message.reply_text("⏰ اختر الملف:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("sched_select:"):
            file_id = data.split(":")[1]
            context.user_data['scheduling_file'] = file_id
            
            keyboard = [
                [InlineKeyboardButton("1x", callback_data="posts:1")],
                [InlineKeyboardButton("2x", callback_data="posts:2")],
                [InlineKeyboardButton("3x", callback_data="posts:3")],
            ]
            await query.edit_message_text("🔢 عدد المرات؟", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data.startswith("posts:"):
            posts = int(data.split(":")[1])
            context.user_data['posts_per_day'] = posts
            
            suggestions = {1: ["09:00", "12:00", "18:00"], 2: ["09:00,21:00"], 3: ["09:00,14:00,20:00"]}
            keyboard = [[InlineKeyboardButton(t, callback_data=f"time:{t}")] for t in suggestions.get(posts, ["09:00"])]
            await query.edit_message_text(f"⏰ التوقيت ({posts}x):", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data.startswith("time:"):
            time_choice = data.split(":")[1]
            await self._confirm_schedule(query, context, [time_choice])
        
        elif data == "confirm_schedule":
            file_id = context.user_data.get('scheduling_file')
            posts = context.user_data.get('posts_per_day', 1)
            times = context.user_data.get('selected_times', ['09:00'])
            
            await self.scheduler.setup_schedule(file_id, posts, times)
            await query.edit_message_text(f"✅ تم التفعيل!\n⏰ {posts}x: {', '.join(times)}")
    
    async def _confirm_schedule(self, query, context, times):
        context.user_data['selected_times'] = times
        keyboard = [[InlineKeyboardButton("✅ تأكيد", callback_data="confirm_schedule")]]
        await query.edit_message_text(f"📋 تأكيد: {', '.join(times)}؟", reply_markup=InlineKeyboardMarkup(keyboard))
    
    @admin_only
    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📢 أرسل @channel أو -100...")
        context.user_data['awaiting_channel'] = True
    
    @admin_only
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if context.user_data.get('awaiting_channel'):
            channel_id = text.strip()
            
            if not (channel_id.startswith('@') or channel_id.startswith('-100')):
                await update.message.reply_text("❌ معرف غير صالح")
                return
            
            success = self.db.add_channel(channel_id, channel_id)
            await update.message.reply_text(f"✅ تمت الإضافة!" if success else "⚠️ موجودة أو خطأ")
            context.user_data['awaiting_channel'] = False
        
        else:
            await update.message.reply_text("❓ /help")
    
    @admin_only
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        jobs_count = len(self.scheduler.scheduler.get_jobs())
        channels = len(self.db.get_channels())
        files = len(self.db.list_phrases())
        
        await update.message.reply_html(f"""
📊 <b>الحالة</b>
🤖 يعمل على Render
⏰ المهام: {jobs_count}
📢 القنوات: {channels}
📁 الملفات: {files}
🌐 Webhook: {"مفعل" if CONFIG.WEBHOOK_URL else "معطل"}
        """)
    
    @admin_only
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_html("""
📖 <b>الدليل</b>
1️⃣ /upload - رفع TXT
2️⃣ /addchannel - إضافة قناة
3️⃣ /schedule - جدولة
4️⃣ /status - الحالة
⚡ يعمل 24/7 مع Keep-Alive
        """)

# ============================================================================
# POST INIT CALLBACK (ثابتة الآن!)
# ============================================================================

async def post_init(application: Application):
    """تهيئة ما بعد بناء التطبيق"""
    logger.info("🚀 Post-init starting...")
    
    # الوصول إلى المتغيرات العالمية
    bot_data = application.bot_data
    
    # إنشاء Scheduler
    scheduler = PublishScheduler(application.bot, bot_data['db'])
    bot_data['scheduler'] = scheduler
    
    # إنشاء Handlers
    handlers = BotHandlers(bot_data['db'], scheduler)
    bot_data['handlers'] = handlers
    
    # تسجيل المعالجات
    _register_handlers(application, handlers)
    
    # إعداد الأوامر
    await _setup_commands(application)
    
    # بدء Self-Ping
    if CONFIG.RENDER_EXTERNAL_URL:
        self_ping = SelfPing(CONFIG.RENDER_EXTERNAL_URL, interval=600)
        self_ping.start()
    
    logger.info("✅ Bot initialized!")

def _register_handlers(app: Application, handlers: BotHandlers):
    h = handlers
    
    app.add_handler(CommandHandler("start", h.start))
    app.add_handler(CommandHandler("help", h.help_command))
    app.add_handler(CommandHandler("upload", h.upload_file))
    app.add_handler(CommandHandler("list", h.list_files))
    app.add_handler(CommandHandler("schedule", h.schedule_command))
    app.add_handler(CommandHandler("addchannel", h.add_channel))
    app.add_handler(CommandHandler("status", h.status))
    
    app.add_handler(MessageHandler(filters.Document.TXT, h.handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h.text_handler))
    app.add_handler(CallbackQueryHandler(h.callback_handler))
    
    app.add_error_handler(_error_handler)

async def _setup_commands(app: Application):
    commands = [
        BotCommand("start", "بدء"),
        BotCommand("upload", "رفع ملف"),
        BotCommand("list", "الملفات"),
        BotCommand("schedule", "جدولة"),
        BotCommand("addchannel", "إضافة قناة"),
        BotCommand("status", "الحالة"),
        BotCommand("help", "مساعدة"),
    ]
    await app.bot.set_my_commands(commands)

async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ خطأ!")

# ============================================================================
# MAIN
# ============================================================================

def main():
    if not CONFIG.validate():
        return
    
    # تشغيل Keep-Alive Server
    start_keep_alive_server(port=8080)
    
    # إنشاء قاعدة البيانات
    db = Database()
    
    # بناء التطبيق مع post_init
    application = (
        ApplicationBuilder()
        .token(CONFIG.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # تخزين DB في bot_data للوصول لاحقاً
    application.bot_data['db'] = db
    
    # تشغيل Webhook أو Polling
    if CONFIG.RENDER_EXTERNAL_URL and CONFIG.WEBHOOK_URL:
        logger.info(f"🚀 WEBHOOK mode: {CONFIG.WEBHOOK_URL}")
        
        application.run_webhook(
            listen="0.0.0.0",
            port=CONFIG.PORT,
            webhook_url=CONFIG.WEBHOOK_URL,
            secret_token=CONFIG.WEBHOOK_SECRET,
        )
    else:
        logger.info("🔄 POLLING mode")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
