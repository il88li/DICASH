#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🎩 بوت النكد الشيك (Elegant Melancholy Bot) 🎩             ║
║                                                                              ║
║   بوت تلجرام متطور يولد محتوى ساخر بأسلوب شاب مصري أنيق وبائس               ║
║   يعمل بنظام Webhook على Flask + Render                                     ║
║                                                                              ║
║   المحرك الذكي: Gemini 1.5 Flash (Google)                                    ║
║   الشخصية: شاب مصري في العشرينيات، OCD، قلق اجتماعي، سخرية سوداء            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 الإعدادات المطلوبة (Environment Variables):
   - BOT_TOKEN: توكن البوت من @BotFather
   - GEMINI_API_KEY: مفتاح Gemini من Google AI Studio
   - WEBHOOK_URL: رابط موقعك على Render
   - PORT: المنفذ (Render يحدده تلقائياً)

🚀 للتشغيل:
   python bot.py
   
   أو مع Gunicorn (للإنتاج):
   gunicorn bot:app --bind 0.0.0.0:$PORT
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 📦 الاستيرادات
# ═══════════════════════════════════════════════════════════════════════════════

import os
import json
import logging
import random
import google.generativeai as genai
from flask import Flask, request, abort
from telebot import TeleBot, types
from datetime import datetime
import time

# ═══════════════════════════════════════════════════════════════════════════════
# ⚙️ الإعدادات والمتغيرات
# ═══════════════════════════════════════════════════════════════════════════════

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# تهيئة Flask
app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 🔐 إعدادات البوت (من متغيرات البيئة)
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://dicash.onrender.com')
PORT = int(os.environ.get('PORT', 10000))

# التحقق من وجود المتغيرات المطلوبة
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير محدد! تأكد من إضافته في متغيرات البيئة")
if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY غير محدد! تأكد من إضافته في متغيرات البيئة")
if not WEBHOOK_URL:
    logger.error("❌ WEBHOOK_URL غير محدد! تأكد من إضافته في متغيرات البيئة")

# ═══════════════════════════════════════════════════════════════════════════════
# 🤖 تهيئة البوت والذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════════════════

bot = TeleBot(BOT_TOKEN, threaded=False)

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Gemini AI تم تهيئته بنجاح")
except Exception as e:
    logger.error(f"❌ فشل تهيئة Gemini: {e}")
    model = None

# ═══════════════════════════════════════════════════════════════════════════════
# 💾 قاعدة البيانات المؤقتة (في الذاكرة)
# ═══════════════════════════════════════════════════════════════════════════════

user_data = {}
channel_settings = {}

# ═══════════════════════════════════════════════════════════════════════════════
# 📝 العبارات الاحتياطية (مضمنة في الكود)
# ═══════════════════════════════════════════════════════════════════════════════

FALLBACK_PHRASES = [
    "لبسني السترة ونسي يدفيني",
    "بنضف الشقة وبننسى نضف الروح",
    "أناقة برا وخراب جوا، زي الفرق بين الديكور والبيت",
    "بشتري هدوم جديدة وبنفسي القديم",
    "بنظف الشاشة وبننسى نظف القلب",
    "أنيق في الملبس، مكسور في الحس",
    "بنكحت الكرافتة وبننسى نكحت الحياة",
    "بنرص الكتب وبننسى نرتب أفكاري",
    "عطري فرنسي وهمي مصري",
    "بنلم البيت وبننسى نلم نفسي",
    "نظاراتي برادا وعيني على البلد",
    "بنكوي القميص وبننسى نكوي الروح",
    "حذائي جلد طبيعي ومشيي على صفيح ساخن",
    "بنرص الحذاء عالرصيف وبنمشي على الأرض",
    "ساعتي سويسري ووقتي ضايع",
    "بنضف المراية وبشوفش نفسي",
    "بنشتري عطر وبننسى نعطر الأيام",
    "أنيق برا، ملخبط جوا، زي الدرج من تحت",
    "بنلم الشعر وبننسى نلم الأفكار",
    "بدلة كاملة وروح ناقصة"
]

# ═══════════════════════════════════════════════════════════════════════════════
# 🎭 البرومبت الأساسي (Master Prompt)
# ═══════════════════════════════════════════════════════════════════════════════

MASTER_PROMPT = """أنت شاب مصري في مقتبل العشرينيات، تتمتع بأناقة عالية رغم العيش وسط ظروف صعبة. 
مصاب بالوسواس القهري (OCD) والقلق الاجتماعي، وتميل إلى السخرية السوداء المستوحاة من أدب ديستويفسكي وأغاني كايروكي.

اكتب عبارة ساخرة لا تتجاوز 30 حرفاً، تعتمد على القافية الشعبية (السجع)، 
تعبر عن التناقض بين الأناقة الخارجية والخراب الداخلي، 
دون التطرق للسياسة أو الدين أو أي مواضيع حساسة.

العبارة يجب أن:
1. تكون باللهجة المصرية الدارجة
2. تستخدم قافية إيقاعية (مثل: "الكلام - السلام"، "الدنيا - الدنية")
3. تعبر عن الحزن بأسلوب أنيق وساخر
4. لا تتجاوز 30 حرفاً
5. تكون مناسبة للنشر على السوشيال ميديا

اكتب العبارة فقط بدون أي تعليقات إضافية."""

# ═══════════════════════════════════════════════════════════════════════════════
# 🛠️ دوال المساعدة
# ═══════════════════════════════════════════════════════════════════════════════

def get_user_data(user_id):
    """الحصول على بيانات المستخدم أو إنشاءها"""
    if user_id not in user_data:
        user_data[user_id] = {
            'channel_id': None,
            'channel_name': None,
            'last_phrase': None,
            'generated_count': 0,
            'posted_count': 0
        }
    return user_data[user_id]

def generate_melancholy_phrase():
    """توليد عبارة نكد جديدة باستخدام Gemini"""
    if model is None:
        logger.warning("⚠️ Gemini غير متوفر، استخدام عبارة احتياطية")
        return random.choice(FALLBACK_PHRASES)
    
    try:
        response = model.generate_content(MASTER_PROMPT)
        phrase = response.text.strip()
        # تنظيف العبارة
        phrase = phrase.replace('"', '').replace("'", "")
        if len(phrase) > 100:
            phrase = phrase[:100] + "..."
        return phrase
    except Exception as e:
        logger.error(f"❌ خطأ في توليد العبارة: {e}")
        return random.choice(FALLBACK_PHRASES)

def create_main_keyboard():
    """إنشاء لوحة التحكم الرئيسية"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    btn_generate = types.InlineKeyboardButton(
        text="📝 توليد عبارة الآن", 
        callback_data="generate_now"
    )
    btn_post = types.InlineKeyboardButton(
        text="📤 نشر في القناة", 
        callback_data="post_to_channel"
    )
    btn_set_channel = types.InlineKeyboardButton(
        text="⚙️ تعيين القناة", 
        callback_data="set_channel"
    )
    btn_preview = types.InlineKeyboardButton(
        text="👁️ معاينة العبارة", 
        callback_data="preview_phrase"
    )
    btn_stats = types.InlineKeyboardButton(
        text="📊 الإحصائيات", 
        callback_data="show_stats"
    )
    btn_help = types.InlineKeyboardButton(
        text="❓ المساعدة", 
        callback_data="show_help"
    )
    
    keyboard.add(btn_generate, btn_post)
    keyboard.add(btn_set_channel, btn_preview)
    keyboard.add(btn_stats, btn_help)
    
    return keyboard

def is_user_admin(channel_id, user_id):
    """التحقق إذا كان المستخدم أدمن في القناة"""
    try:
        member = bot.get_chat_member(channel_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من الصلاحيات: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# 📨 معالجات الأوامر
# ═══════════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def handle_start(message):
    """معالج أمر البداية"""
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    welcome_text = f"""👋 أهلاً بيك في *بوت النكد الشيك*!

أنا شاب مصري أنيق وبائس، بكتب عبارات ساخرة عن التناقض بين الأناقة والخراب.

📌 *حالتك الحالية:*
• القناة المربوطة: {user['channel_name'] if user['channel_name'] else 'غير محددة'}
• العبارات المولدة: {user['generated_count']}
• المنشورات المنشورة: {user['posted_count']}

اختار من لوحة التحكم:
"""
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard()
    )

@bot.message_handler(commands=['help'])
def handle_help(message):
    """معالج أمر المساعدة"""
    help_text = """📖 *دليل استخدام بوت النكد الشيك*

*الأوامر المتاحة:*
/start - فتح لوحة التحكم الرئيسية
/help - عرض هذا الدليل
/generate - توليد عبارة نكد جديدة
/channel - تعيين القناة المستهدفة
/post - نشر عبارة في القناة

*خطوات الإعداد:*
1️⃣ أضف البوت كمشرف في قناتك
2️⃣ ارسل /channel وحدد معرف القناة
3️⃣ اضغط "توليد عبارة الآن" للحصول على مسودة
4️⃣ اضغط "نشر في القناة" لنشرها

*ملاحظات:*
• يجب أن يكون البوت مشرفاً في القناة
• العبارات تُولد تلقائياً بالذكاء الاصطناعي
• يمكنك المعاينة قبل النشر
"""
    bot.send_message(
        message.chat.id,
        help_text,
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['generate'])
def handle_generate_command(message):
    """معالج أمر التوليد المباشر"""
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    # إرسال رسالة "جاري التوليد"
    processing_msg = bot.send_message(
        message.chat.id,
        "⏳ جاري توليد عبارة النكد الشيك..."
    )
    
    # توليد العبارة
    phrase = generate_melancholy_phrase()
    user['last_phrase'] = phrase
    user['generated_count'] += 1
    
    # حذف رسالة التحميل
    bot.delete_message(message.chat.id, processing_msg.message_id)
    
    # إرسال العبارة مع خيارات
    keyboard = types.InlineKeyboardMarkup()
    btn_regenerate = types.InlineKeyboardButton(
        text="🔄 توليد جديد", 
        callback_data="generate_now"
    )
    btn_post = types.InlineKeyboardButton(
        text="📤 نشر في القناة", 
        callback_data="post_to_channel"
    )
    keyboard.add(btn_regenerate, btn_post)
    
    bot.send_message(
        message.chat.id,
        f"✨ *عبارة النكد الشيك:*\n\n_{phrase}_",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

@bot.message_handler(commands=['channel'])
def handle_channel_command(message):
    """معالج أمر تعيين القناة"""
    msg = bot.send_message(
        message.chat.id,
        """📢 *تعيين القناة*

أرسل معرف القناة (Channel ID) أو قم بإعادة توجيه أي رسالة من القناة.

*مثال:* `-1001234567890`

⚠️ تأكد أن:
• البوت مضاف للقناة كمشرف
• لديك صلاحيات الأدمن في القناة""",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_channel_id)

def process_channel_id(message):
    """معالجة معرف القناة"""
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    channel_id = message.text.strip()
    
    # التحقق من صحة المعرف
    if not (channel_id.startswith('-100') or channel_id.startswith('@')):
        bot.send_message(
            message.chat.id,
            "❌ معرف القناة غير صحيح. يجب أن يبدأ بـ -100 أو @"
        )
        return
    
    # التحقق من صلاحيات المستخدم
    try:
        if is_user_admin(channel_id, user_id):
            chat_info = bot.get_chat(channel_id)
            user['channel_id'] = channel_id
            user['channel_name'] = chat_info.title
            
            bot.send_message(
                message.chat.id,
                f"✅ تم ربط البوت بالقناة: *{chat_info.title}*\n\nيمكنك الآن النشر مباشرة!",
                parse_mode='Markdown',
                reply_markup=create_main_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ ليس لديك صلاحيات الأدمن في هذه القناة، أو البوت ليس مشرفاً."
            )
    except Exception as e:
        logger.error(f"❌ خطأ في تعيين القناة: {e}")
        bot.send_message(
            message.chat.id,
            "❌ حدث خطأ. تأكد أن البوت مضاف للقناة كمشرف وأن المعرف صحيح."
        )

@bot.message_handler(commands=['post'])
def handle_post_command(message):
    """معالج أمر النشر"""
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    if not user['channel_id']:
        bot.send_message(
            message.chat.id,
            "❌ لم يتم تعيين قناة بعد. استخدم /channel أولاً."
        )
        return
    
    if not user['last_phrase']:
        bot.send_message(
            message.chat.id,
            "❌ لا توجد عبارة محفوظة. استخدم /generate أولاً."
        )
        return
    
    try:
        bot.send_message(
            user['channel_id'],
            f"_{user['last_phrase']}_\n\n#نكد_شيك #نكد_يومي",
            parse_mode='Markdown'
        )
        user['posted_count'] += 1
        bot.send_message(
            message.chat.id,
            "✅ تم النشر بنجاح في القناة!",
            reply_markup=create_main_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في النشر: {e}")
        bot.send_message(
            message.chat.id,
            "❌ فشل النشر. تأكد من صلاحيات البوت في القناة."
        )

# ═══════════════════════════════════════════════════════════════════════════════
# 🔘 معالجات الأزرار (Callbacks)
# ═══════════════════════════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda call: call.data == 'generate_now')
def callback_generate(call):
    """معالج زر التوليد"""
    user_id = call.from_user.id
    user = get_user_data(user_id)
    
    # تعديل الرسالة الحالية
    bot.edit_message_text(
        "⏳ جاري توليد عبارة النكد الشيك...",
        call.message.chat.id,
        call.message.message_id
    )
    
    # توليد العبارة
    phrase = generate_melancholy_phrase()
    user['last_phrase'] = phrase
    user['generated_count'] += 1
    
    # إنشاء لوحة المفاتيح
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_regenerate = types.InlineKeyboardButton(
        text="🔄 توليد جديد", 
        callback_data="generate_now"
    )
    btn_post = types.InlineKeyboardButton(
        text="📤 نشر في القناة", 
        callback_data="post_to_channel"
    )
    btn_back = types.InlineKeyboardButton(
        text="🔙 العودة للقائمة", 
        callback_data="back_to_menu"
    )
    keyboard.add(btn_regenerate, btn_post)
    keyboard.add(btn_back)
    
    bot.edit_message_text(
        f"✨ *عبارة النكد الشيك:*\n\n_{phrase}_",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == 'post_to_channel')
def callback_post(call):
    """معالج زر النشر"""
    user_id = call.from_user.id
    user = get_user_data(user_id)
    
    if not user['channel_id']:
        bot.answer_callback_query(
            call.id,
            "❌ لم يتم تعيين قناة بعد!",
            show_alert=True
        )
        return
    
    if not user['last_phrase']:
        bot.answer_callback_query(
            call.id,
            "❌ لا توجد عبارة محفوظة!",
            show_alert=True
        )
        return
    
    try:
        bot.send_message(
            user['channel_id'],
            f"_{user['last_phrase']}_\n\n#نكد_شيك #نكد_يومي",
            parse_mode='Markdown'
        )
        user['posted_count'] += 1
        
        bot.answer_callback_query(
            call.id,
            "✅ تم النشر بنجاح!",
            show_alert=True
        )
        
        # تحديث الرسالة
        bot.edit_message_text(
            f"✅ تم النشر بنجاح!\n\nالعبارة:\n_{user['last_phrase']}_",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=create_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في النشر: {e}")
        bot.answer_callback_query(
            call.id,
            "❌ فشل النشر. تأكد من الصلاحيات!",
            show_alert=True
        )

@bot.callback_query_handler(func=lambda call: call.data == 'set_channel')
def callback_set_channel(call):
    """معالج زر تعيين القناة"""
    msg = bot.send_message(
        call.message.chat.id,
        """📢 *تعيين القناة*

أرسل معرف القناة (Channel ID) أو قم بإعادة توجيه أي رسالة من القناة.

*مثال:* `-1001234567890`

⚠️ تأكد أن:
• البوت مضاف للقناة كمشرف
• لديك صلاحيات الأدمن في القناة""",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_channel_id)

@bot.callback_query_handler(func=lambda call: call.data == 'preview_phrase')
def callback_preview(call):
    """معالج زر المعاينة"""
    user_id = call.from_user.id
    user = get_user_data(user_id)
    
    if not user['last_phrase']:
        bot.answer_callback_query(
            call.id,
            "❌ لا توجد عبارة محفوظة! اضغط توليد أولاً.",
            show_alert=True
        )
        return
    
    preview_text = f"""👁️ *معاينة العبارة:*

_{user['last_phrase']}_

*كيف ستظهر في القناة:*

_{user['last_phrase']}_

#نكد_شيك #نكد_يومي
"""
    
    bot.send_message(
        call.message.chat.id,
        preview_text,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'show_stats')
def callback_stats(call):
    """معالج زر الإحصائيات"""
    user_id = call.from_user.id
    user = get_user_data(user_id)
    
    stats_text = f"""📊 *إحصائياتك:*

📌 القناة المربوطة: {user['channel_name'] if user['channel_name'] else 'غير محددة'}
📝 العبارات المولدة: {user['generated_count']}
📤 المنشورات المنشورة: {user['posted_count']}

آخر عبارة مولدة:
_{user['last_phrase'] if user['last_phrase'] else 'لا يوجد'}_
"""
    
    bot.edit_message_text(
        stats_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'show_help')
def callback_help(call):
    """معالج زر المساعدة"""
    help_text = """❓ *المساعدة السريعة*

📝 *توليد عبارة* - إنشاء عبارة نكد جديدة بالذكاء الاصطناعي
📤 *نشر في القناة* - نشر آخر عبارة مولدة
⚙️ *تعيين القناة* - ربط البوت بقناتك
👁️ *معاينة* - رؤية كيف ستظهر العبارة

*للأوامر الكاملة:* /help
"""
    
    bot.edit_message_text(
        help_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_menu')
def callback_back(call):
    """معالج زر العودة للقائمة"""
    user_id = call.from_user.id
    user = get_user_data(user_id)
    
    welcome_text = f"""👋 أهلاً بيك في *بوت النكد الشيك*!

📌 *حالتك الحالية:*
• القناة المربوطة: {user['channel_name'] if user['channel_name'] else 'غير محددة'}
• العبارات المولدة: {user['generated_count']}
• المنشورات المنشورة: {user['posted_count']}

اختار من لوحة التحكم:
"""
    
    bot.edit_message_text(
        welcome_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard()
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 🌐 Flask Routes (Webhook)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return """
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>بوت النكد الشيك</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                text-align: center; 
                padding: 50px 20px;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container { 
                max-width: 600px; 
                margin: 0 auto;
                background: rgba(255,255,255,0.05);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1);
            }
            h1 { 
                color: #e94560; 
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .subtitle {
                color: #a0a0a0;
                font-size: 1.1em;
                margin-bottom: 30px;
            }
            .status { 
                background: linear-gradient(135deg, rgba(233, 69, 96, 0.2), rgba(15, 52, 96, 0.2)); 
                padding: 25px; 
                border-radius: 15px;
                margin-top: 20px;
                border: 1px solid rgba(233, 69, 96, 0.3);
            }
            .status h2 { 
                color: #00d9ff;
                margin-bottom: 10px;
            }
            .status p {
                color: #a0a0a0;
            }
            .features {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-top: 30px;
            }
            .feature {
                background: rgba(255,255,255,0.05);
                padding: 15px;
                border-radius: 10px;
                font-size: 0.9em;
            }
            .footer {
                margin-top: 30px;
                color: #666;
                font-size: 0.8em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎩 بوت النكد الشيك</h1>
            <p class="subtitle">أنيق من برا، خراب من جوا</p>
            
            <div class="status">
                <h2>✅ البوت يعمل بنجاح</h2>
                <p>Webhook مفعل ويعمل بكامل طاقته</p>
            </div>
            
            <div class="features">
                <div class="feature">🤖 Gemini AI</div>
                <div class="feature">📝 توليد تلقائي</div>
                <div class="feature">📤 نشر مباشر</div>
                <div class="feature">⚙️ لوحة تحكم</div>
            </div>
            
            <div class="footer">
                <p>تم التطوير بـ ❤️ للمحتوى العربي الساخر</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    """نقطة نهاية Webhook"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

@app.route('/health')
def health_check():
    """فحص صحة البوت"""
    return {
        'status': 'healthy',
        'bot': 'Elegant Melancholy Bot',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 🚀 التشغيل الرئيسي
# ═══════════════════════════════════════════════════════════════════════════════

def setup_webhook():
    """إعداد Webhook"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"{WEBHOOK_URL}/webhook"
        bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook مُعد: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ خطأ في إعداد Webhook: {e}")

if __name__ == '__main__':
    logger.info("🎩 بوت النكد الشيك - بدء التشغيل...")
    logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}/webhook")
    
    # إعداد Webhook
    setup_webhook()
    
    # تشغيل Flask
    app.run(host='0.0.0.0', port=PORT)
