#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Scheduler Bot - Render Edition v3.2
Fixed: Early handler registration, webhook setup
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
    filters
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
    RENDER_INTERNAL_HOSTNAME: str = os.getenv("RENDER_INTERNAL_HOSTNAME", "0.0.0.0")
    TIMEZONE: str = os.getenv("TZ", "Asia/Riyadh")
    
    @property
    def WEBHOOK_URL(self) -> str:
        if self.RENDER_EXTERNAL_URL:
            base = self.RENDER_EXTERNAL_URL.rstrip('/')
            return f"{base}/webhook"
        return ""
    
    @property
    def WEBHOOK_SECRET(self) -> str:
        if ':' in self.BOT_TOKEN:
            return self.BOT_TOKEN.split(':')[1]
        return "default_secret_12345"
    
    def validate(self) -> bool:
        if not self.BOT_TOKEN or len(self.BOT_TOKEN) < 20:
            logging.error("❌ BOT_TOKEN غير صالح!")
            return False
        if self.ADMIN_ID == 0:
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
# KEEP-ALIVE SERVER (منفذ منفصل 8080)
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
            "webhook": CONFIG.WEBHOOK_URL,
            "admin_id": str(CONFIG.ADMIN_ID)
        }
        self.wfile.write(json.dumps(response).encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_keep_alive_server(port: int = 8080):
    def run():
        try:
            server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
            logger.info(f"🌐 Keep-Alive Server: port {port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Keep-Alive error: {e}")
    
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t

# ============================================================================
# SELF-PING (للحفاظ على استيقاظ Render)
# ============================================================================

class SelfPing:
    def __init__(self, url: str, interval: int = 300):  # كل 5 دقائق
        self.url = url
        self.interval = interval
        self.running = False
    
    def start(self):
        if not self.url or self.running:
            return
        
        self.running = True
        
        def ping():
            import urllib.request
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            while self.running:
                try:
                    req = urllib.request.Request(
                        f"{self.url}/webhook",  # ping the webhook path
                        method='HEAD',
                        headers={'User-Agent': 'KeepAlive/1.0'},
                        timeout=10
                    )
                    with urllib.request.urlopen(req, context=ctx) as r:
                        logger.info(f"💓 Self-Ping: {r.status}")
                except Exception as e:
                    logger.warning(f"Self-Ping: {e}")
                time.sleep(self.interval)
        
        threading.Thread(target=ping, daemon=True).start()
        logger.info(f"🔄 Self-Ping started")

# ============================================================================
# DATABASE
# ============================================================================

class Database:
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
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
            c = conn.cursor()
            c.execute("""
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
            c.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    channel_name TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase_file_id TEXT,
                    posts_per_day INTEGER DEFAULT 3,
                    times TEXT,
                    is_active BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
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
            c = conn.cursor()
            c.execute("""
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
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    phrases.append(match.group(1).strip())
                    break
            else:
                if len(line) > 3:
                    phrases.append(line)
        return phrases
    
    def get_next_phrase(self, file_id: str) -> Optional[str]:
        with self.connection() as conn:
            c = conn.cursor()
            c.execute("SELECT content, current_index, total_count FROM phrases WHERE file_id = ?", (file_id,))
            row = c.fetchone()
            
            if not row or row['current_index'] >= row['total_count']:
                return None
            
            phrases = json.loads(row['content'])
            result = phrases[row['current_index']]
            
            c.execute("UPDATE phrases SET current_index = current_index + 1 WHERE file_id = ?", (file_id,))
            return result
    
    def add_channel(self, channel_id: str, channel_name: str = "") -> bool:
        try:
            with self.connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO channels (channel_id, channel_name) VALUES (?, ?)", 
                         (channel_id, channel_name))
                return c.rowcount > 0
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            return False
    
    def get_channels(self) -> List[Dict]:
        with self.connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM channels WHERE is_active = 1")
            return [dict(row) for row in c.fetchall()]
    
    def list_phrases(self) -> List[Dict]:
        with self.connection() as conn:
            c = conn.cursor()
            c.execute("SELECT file_id, file_name, total_count, current_index, is_active FROM phrases ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    def set_schedule(self, file_id: str, posts_per_day: int, times: List[str]) -> int:
        with self.connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO schedules (phrase_file_id, posts_per_day, times, is_active)
                VALUES (?, ?, ?, 1)
            """, (file_id, posts_per_day, json.dumps(times)))
            return c.lastrowid

# ============================================================================
# SCHEDULER
# ============================================================================

class PublishScheduler:
    def __init__(self, bot, db: Database):
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=CONFIG.TIMEZONE)
        self.scheduler.start()
        logger.info("✅ Scheduler ready")
    
    async def setup_schedule(self, file_id: str, posts_per_day: int, times: List[str]):
        # إزالة القديم
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"pub_{file_id}"):
                job.remove()
        
        self.db.set_schedule(file_id, posts_per_day, times)
        
        for t in times:
            hour, minute = map(int, t.split(':'))
            job_id = f"pub_{file_id}_{t.replace(':', '')}"
            self.scheduler.add_job(
                self.publish_job,
                CronTrigger(hour=hour, minute=minute),
                id=job_id,
                args=[file_id],
                replace_existing=True
            )
            logger.info(f"⏰ Job: {job_id} at {t}")
    
    async def publish_job(self, file_id: str):
        try:
            phrase = self.db.get_next_phrase(file_id)
            if not phrase:
                await self.bot.send_message(CONFIG.ADMIN_ID, "✅ انتهت العبارات!")
                for job in self.scheduler.get_jobs():
                    if job.id.startswith(f"pub_{file_id}"):
                        job.remove()
                return
            
            channels = self.db.get_channels()
            for ch in channels:
                try:
                    await self.bot.send_message(ch['channel_id'], phrase, parse_mode='HTML')
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Send error: {e}")
        except Exception as e:
            logger.error(f"Publish error: {e}")

# ============================================================================
# HANDLERS (مع التحقق من المدير)
# ============================================================================

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return
        if update.effective_user.id != CONFIG.ADMIN_ID:
            await update.message.reply_text("⛔ Unauthorized!")
            logger.warning(f"Blocked user: {update.effective_user.id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ----- Command Handlers -----

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    logger.info(f"🎯 /start received from {update.effective_user.id}")
    
    await update.message.reply_html("""
🤖 <b>Bot Scheduler Pro</b> - يعمل!

📁 /upload - رفع ملف TXT
📋 /list - قائمة الملفات  
⏰ /schedule - جدولة النشر
📢 /addchannel - إضافة قناة
📊 /status - حالة النظام
❓ /help - المساعدة

✅ البوت متصل ويعمل
    """)

@admin_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("استخدم /start للقائمة الرئيسية")

@admin_only
async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 أرسل ملف TXT الآن")
    context.user_data['awaiting_file'] = True

@admin_only
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data['db']
    files = db.list_phrases()
    
    if not files:
        await update.message.reply_text("📭 لا توجد ملفات")
        return
    
    text = "📁 <b>ملفاتك:</b>\n\n"
    for f in files:
        prog = f"{f['current']}/{f['total']}"
        text += f"• {f['file_name'][:25]}... ({prog})\n"
    
    await update.message.reply_html(text)

@admin_only
async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data['db']
    files = db.list_phrases()
    
    if not files:
        await update.message.reply_text("❌ لا توجد ملفات! استخدم /upload أولاً")
        return
    
    keyboard = []
    for f in files:
        if f['current'] < f['total']:
            btn = f"📄 {f['file_name'][:20]} ({f['current']}/{f['total']})"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"sel:{f['file_id']}")])
    
    await update.message.reply_text("⏰ اختر الملف:", reply_markup=InlineKeyboardMarkup(keyboard))

@admin_only
async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 أرسل معرف القناة:\n<code>@channelname</code> أو <code>-1001234567890</code>", parse_mode='HTML')
    context.user_data['awaiting_channel'] = True

@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scheduler = context.bot_data.get('scheduler')
    db = context.bot_data['db']
    
    jobs len(scheduler.scheduler.get_jobs()) if scheduler else 0
    ch = len(db.get_channels())
    files = len(db.list_phrases())
    
    await update.message.reply_html(f"""
📊 <b>حالة النظام</b>
🤖 البوت: <b>يعمل</b> ✅
⏰ المهام النشطة: {jobs}
📢 القنوات: {ch}
📁 الملفات: {files}
🔧 Webhook: {"مفعل" if CONFIG.WEBHOOK_URL else "معطل"}
🆔 Admin: {CONFIG.ADMIN_ID}
    """)

# ----- Message Handlers -----

@admin_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_file'):
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ يجب أن يكون الملف .txt")
        return
    
    file = await context.bot.get_file(doc.file_id)
    path = f"temp_{doc.file_id}.txt"
    await file.download_to_drive(path)
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        db = context.bot_data['db']
        count = db.save_phrases(doc.file_id, doc.file_name, content)
        
        await update.message.reply_text(f"✅ تم حفظ {count} عبارة!")
        
        keyboard = [[InlineKeyboardButton("⏰ جدولة الآن", callback_data=f"sched:{doc.file_id}")]]
        await update.message.reply_text("ماذا تريد؟", reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)
        context.user_data['awaiting_file'] = False

@admin_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if context.user_data.get('awaiting_channel'):
        ch_id = text.strip()
        if not (ch_id.startswith('@') or ch_id.startswith('-100')):
            await update.message.reply_text("❌ معرف غير صالح")
            return
        
        db = context.bot_data['db']
        success = db.add_channel(ch_id, ch_id)
        await update.message.reply_text("✅ تمت الإضافة!" if success else "⚠️ موجودة مسبقاً")
        context.user_data['awaiting_channel'] = False
    else:
        await update.message.reply_text("❓ استخدم /start للأوامر")

# ----- Callback Handler -----

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    db = context.bot_data['db']
    scheduler = context.bot_data['scheduler']
    
    if data.startswith("sel:"):
        file_id = data[4:]
        context.user_data['sched_file'] = file_id
        
        keyboard = [
            [InlineKeyboardButton("1x يومياً", callback_data="n:1")],
            [InlineKeyboardButton("2x يومياً", callback_data="n:2")],
            [InlineKeyboardButton("3x يومياً", callback_data="n:3")],
        ]
        await query.edit_message_text("🔢 عدد مرات النشر؟", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("n:"):
        n = int(data[2:])
        context.user_data['sched_n'] = n
        
        times = {1: ["09:00", "15:00", "20:00"], 2: ["09:00,21:00"], 3: ["09:00,15:00,21:00"]}
        keyboard = [[InlineKeyboardButton(t, callback_data=f"t:{t}")] for t in times.get(n, ["09:00"])]
        await query.edit_message_text(f"⏰ اختر التوقيت ({n}x):", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("t:"):
        t = data[2:]
        context.user_data['sched_times'] = [t]
        
        keyboard = [[InlineKeyboardButton("✅ تأكيد", callback_data="confirm")]]
        await query.edit_message_text(f"تأكيد الجدولة: {t}؟", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "confirm":
        file_id = context.user_data.get('sched_file')
        n = context.user_data.get('sched_n', 1)
        times = context.user_data.get('sched_times', ['09:00'])
        
        await scheduler.setup_schedule(file_id, n, times)
        await query.edit_message_text(f"✅ تم الجدولة!\n⏰ {n}x يومياً: {', '.join(times)}")

# ----- Error Handler -----

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Exception: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ حدث خطأ! تحقق من السجلات.")

# ============================================================================
# SETUP APPLICATION
# ============================================================================

def setup_application(db: Database):
    """إعداد التطبيق مع تسجيل جميع المعالجات"""
    
    # بناء التطبيق
    application = ApplicationBuilder().token(CONFIG.BOT_TOKEN).build()
    
    # تخزين DB في bot_data
    application.bot_data['db'] = db
    
    # تسجيل المعالجات مبكراً (مهم جداً!)
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("upload", cmd_upload))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("schedule", cmd_schedule))
    application.add_handler(CommandHandler("addchannel", cmd_addchannel))
    application.add_handler(CommandHandler("status", cmd_status))
    
    application.add_handler(MessageHandler(filters.Document.TXT, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    application.add_error_handler(error_handler)
    
    logger.info("✅ Handlers registered successfully")
    return application

async def post_init(application: Application):
    """تهيئة ما بعد البدء (Scheduler + Commands + Self-Ping)"""
    logger.info("🚀 Post-init starting...")
    
    # إنشاء Scheduler
    db = application.bot_data['db']
    scheduler = PublishScheduler(application.bot, db)
    application.bot_data['scheduler'] = scheduler
    
    # إعداد الأوامر في Telegram
    await application.bot.set_my_commands([
        BotCommand("start", "بدء البوت"),
        BotCommand("upload", "رفع ملف TXT"),
        BotCommand("list", "قائمة الملفات"),
        BotCommand("schedule", "جدولة النشر"),
        BotCommand("addchannel", "إضافة قناة"),
        BotCommand("status", "حالة النظام"),
        BotCommand("help", "مساعدة"),
    ])
    
    # إعلام المدير بالبدء
    try:
        await application.bot.send_message(
            CONFIG.ADMIN_ID, 
            "🤖 <b>البوت يعمل الآن!</b>\n\n"
            f"🌐 Webhook: <code>{CONFIG.WEBHOOK_URL}</code>\n"
            f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.warning(f"Couldn't notify admin: {e}")
    
    # بدء Self-Ping
    if CONFIG.RENDER_EXTERNAL_URL:
        ping = SelfPing(CONFIG.RENDER_EXTERNAL_URL, interval=300)
        ping.start()
    
    logger.info("✅ Post-init completed!")

# ============================================================================
# MAIN
# ============================================================================

def main():
    # التحقق من الإعدادات
    if not CONFIG.validate():
        logger.error("❌ Configuration invalid!")
        return
    
    # تشغيل Keep-Alive Server (منفذ 8080)
    start_keep_alive_server(port=8080)
    
    # إنشاء قاعدة البيانات
    db = Database()
    logger.info("✅ Database ready")
    
    # إعداد التطبيق (مع تسجيل المعالجات)
    application = setup_application(db)
    
    # Webhook Mode
    if CONFIG.RENDER_EXTERNAL_URL and CONFIG.WEBHOOK_URL:
        logger.info(f"🚀 Starting WEBHOOK mode")
        logger.info(f"🔗 URL: {CONFIG.WEBHOOK_URL}")
        logger.info(f"🔑 Secret: {CONFIG.WEBHOOK_SECRET[:10]}...")
        
        # تشغيل Webhook (بدون post_init في run_webhook!)
        application.run_webhook(
            listen="0.0.0.0",
            port=CONFIG.PORT,
            webhook_url=CONFIG.WEBHOOK_URL,
            secret_token=CONFIG.WEBHOOK_SECRET,
            drop_pending_updates=True,  # تجاهل الرسائل القديمة
        )
        
        # تشغيل post_init يدوياً بعد بدء Webhook
        # ملاحظة: هذا يتطلب event loop نشط
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(post_init(application))
        except Exception as e:
            logger.error(f"Post-init error: {e}")
            
    else:
        # Polling Mode (للتطوير)
        logger.info("🔄 Starting POLLING mode")
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
