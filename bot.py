import os
import json
import schedule
import threading
import time
import random
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai

# ========== إصلاح: تحديد التوكنات مباشرة للتجربة ==========
# يمكنك تجربة وضع التوكنات مباشرة هنا مؤقتاً للتجربة
TOKEN = os.environ.get('TELEGRAM_TOKEN') or "8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4"
GEMINI_KEY = os.environ.get('GEMINI_API_KEY') or "AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE"

# ========== إصلاح: استخدام متغير RENDER الخاص ==========
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
if RENDER_EXTERNAL_URL:
    WEBHOOK_URL = RENDER_EXTERNAL_URL.rstrip('/')
else:
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://dicash.onrender.com').rstrip('/')

print("=" * 60)
print("🔧 بدء تشغيل البوت مع الإعدادات التالية:")
print(f"🤖 TOKEN موجود: {'✅' if TOKEN else '❌'}")
print(f"🧠 GEMINI_KEY موجود: {'✅' if GEMINI_KEY else '❌'}")
print(f"🌐 WEBHOOK_URL: {WEBHOOK_URL}")
print("=" * 60)

# ========== إنشاء المجلدات اللازمة ==========
os.makedirs('data', exist_ok=True)
SETTINGS_FILE = 'data/user_settings.json'

# تحميل الإعدادات
def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {
        'channel': os.environ.get('DEFAULT_CHANNEL', '2904278551'),
        'time': "غير محدد",
        'is_active': False
    }

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except:
        pass

user_settings = load_settings()
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== تهيئة Gemini ==========
GEMINI_AVAILABLE = False
try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        # اختبار سريع
        test = model.generate_content("اكتب 'مرحبا'")
        if test.text:
            GEMINI_AVAILABLE = True
            print("✅ Gemini متصل بنجاح")
except Exception as e:
    print(f"⚠️  تحذير Gemini: {str(e)[:100]}")

# ========== برومبت مُبسط ==========
PROMPT = """أنت شاب مصري برنس في لبسك بس حياتك خرابة من الحرب.
اكتب عبارة مصرية عامية مضحكة-محزنة (25-35 حرف) بتعبر عن تناقضك."""

def generate_quote():
    if not GEMINI_AVAILABLE:
        return "🚬 والله النهاردة مخي مش شغال... جرب تاني"
    try:
        res = model.generate_content(PROMPT)
        quote = res.text.strip()[:50]
        return quote if quote else "😔 مفيش كلام النهاردة"
    except:
        return "🤒 الذكاء تعبان النهاردة"

# ========== الجدولة ==========
def scheduled_posting():
    if user_settings['is_active'] and user_settings['time'] != "غير محدد":
        try:
            quote = generate_quote()
            channel = user_settings['channel']
            if not channel.startswith('@') and not channel.startswith('-100'):
                channel = f"@{channel}" if channel.isdigit() else f"@{channel}"
            bot.send_message(channel, quote)
            print(f"✅ نشر مجدول: {quote[:30]}")
        except Exception as e:
            print(f"❌ خطأ في النشر المجدول: {e}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

if user_settings['time'] != "غير محدد" and user_settings['is_active']:
    try:
        schedule.clear()
        schedule.every().day.at(user_settings['time']).do(scheduled_posting)
    except:
        pass

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# ========== واجهة المستخدم ==========
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"📢 القناة: {user_settings['channel'][:15]}", callback_data="set_channel"),
        InlineKeyboardButton(f"⏰ الوقت: {user_settings['time']}", callback_data="set_time"),
        InlineKeyboardButton(f"{'✅' if user_settings['is_active'] else '❌'} النشر التلقائي", callback_data="toggle_auto"),
        InlineKeyboardButton("🎭 جيب لي نكدة", callback_data="gen_private"),
        InlineKeyboardButton("🚀 نزلها في القناة", callback_data="publish_now")
    )
    return markup

# ========== مسارات Flask ==========
@app.route('/')
def home():
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>🎭 برنس النكد</title></head>
    <body style="text-align:center;padding:50px;font-family:Arial;">
        <h1>🎭 برنس النكد شغال!</h1>
        <p>البوت ID: {bot.get_me().id if hasattr(bot, 'get_me') else 'جار التحميل...'}</p>
        <p>Gemini: {'✅ متصل' if GEMINI_AVAILABLE else '❌ غير متصل'}</p>
        <a href="https://t.me/{(bot.get_me().username if hasattr(bot, 'get_me') else 'bot')}?start=start">🚀 ابدأ مع البوت</a>
        <br><br>
        <a href="/test">🧪 صفحة الاختبار</a>
    </body>
    </html>
    """

@app.route('/test')
def test():
    quote = generate_quote()
    return f"""
    <div style="padding:50px;">
        <h1>🧪 اختبار البوت</h1>
        <p>العبارة: <strong>{quote}</strong></p>
        <p>الطول: {len(quote)} حرف</p>
        <p>Gemini: {'✅' if GEMINI_AVAILABLE else '❌'}</p>
        <p><a href="/">🏠 الرئيسية</a></p>
    </div>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    return "Bad Request", 400

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        result = bot.set_webhook(url=webhook_url)
        return f"""
        <h1>✅ تم تعيين Webhook</h1>
        <p>العنوان: {webhook_url}</p>
        <p>النتيجة: {result}</p>
        <p>معلومات Webhook الحالية: {bot.get_webhook_info()}</p>
        <a href="/">العودة</a>
        """
    except Exception as e:
        return f"<h1>❌ خطأ: {e}</h1>"

@app.route('/get_webhook_info')
def get_webhook_info():
    try:
        info = bot.get_webhook_info()
        return jsonify({
            'url': info.url,
            'has_custom_certificate': info.has_custom_certificate,
            'pending_update_count': info.pending_update_count,
            'last_error_date': info.last_error_date,
            'last_error_message': info.last_error_message
        })
    except Exception as e:
        return jsonify({'error': str(e)})

# ========== معالجة أوامر البوت ==========
@bot.message_handler(commands=['start', 'نكد'])
def start_command(message):
    bot.send_message(
        message.chat.id,
        "🎭 *أهلاً يا برنس في بوت النكد الشيك!*\n\n"
        "تعالى نحبط سوا وننشر نكد شيك في القناة.\n\n"
        "استخدم الأزرار تحت للتحكم:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(message.chat.id, "🆘 اكتب /start علشان تبدأ")

@bot.message_handler(func=lambda m: True)
def echo_all(message):
    bot.send_message(message.chat.id, "🚀 اكتب /start علشان تبدأ")

# ========== معالجة الأزرار ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "gen_private":
        quote = generate_quote()
        bot.send_message(call.message.chat.id, f"🎭 *تفضل:*\n\n`{quote}`", parse_mode="Markdown")
        bot.answer_callback_query(call.id, "✅ جهزت لك")
    
    elif call.data == "publish_now":
        try:
            quote = generate_quote()
            channel = user_settings['channel']
            if not channel.startswith('@') and not channel.startswith('-100'):
                channel = f"@{channel}" if channel.isdigit() else f"@{channel}"
            bot.send_message(channel, quote)
            bot.send_message(call.message.chat.id, f"✅ *نشرت في القناة:*\n\n{quote}", parse_mode="Markdown")
            bot.answer_callback_query(call.id, "✅ تم النشر")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ فشل النشر: {str(e)[:100]}")
    
    elif call.data == "set_channel":
        msg = bot.send_message(call.message.chat.id, "📢 أرسل معرف القناة (@username):")
        bot.register_next_step_handler(msg, lambda m: update_channel(m, call))
    
    elif call.data == "set_time":
        msg = bot.send_message(call.message.chat.id, "⏰ أرسل الوقت (مثل 14:30):")
        bot.register_next_step_handler(msg, lambda m: update_time(m, call))
    
    elif call.data == "toggle_auto":
        user_settings['is_active'] = not user_settings['is_active']
        save_settings(user_settings)
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=main_menu()
        )
        status = "مفعل ✅" if user_settings['is_active'] else "معطل ❌"
        bot.answer_callback_query(call.id, f"النشر التلقائي: {status}")

def update_channel(message, call):
    user_settings['channel'] = message.text
    save_settings(user_settings)
    bot.send_message(message.chat.id, f"✅ تم تغيير القناة لـ: {message.text}", reply_markup=main_menu())

def update_time(message, call):
    user_settings['time'] = message.text
    save_settings(user_settings)
    bot.send_message(message.chat.id, f"✅ تم ضبط الوقت لـ: {message.text}", reply_markup=main_menu())

# ========== تشغيل التطبيق ==========
if __name__ == "__main__":
    print("🚀 بدء تشغيل Flask...")
    
    # محاولة إعداد Webhook تلقائياً
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        print(f"🌐 محاولة تعيين Webhook على: {webhook_url}")
        
        # إزالة أي Webhook سابق
        bot.remove_webhook()
        time.sleep(2)
        
        # تعيين Webhook جديد
        success = bot.set_webhook(url=webhook_url)
        print(f"✅ تم تعيين Webhook: {success}")
        
        # الحصول على معلومات البوت
        bot_info = bot.get_me()
        print(f"🤖 البوت: @{bot_info.username}")
        print(f"👑 الاسم: {bot_info.first_name}")
        print(f"🆔 ID: {bot_info.id}")
        
    except Exception as e:
        print(f"⚠️  تحذير Webhook: {e}")
        print("📡 البوت سيعمل بدون Webhook (للتطوير المحلي)")
    
    # تشغيل Flask
    port = int(os.environ.get("PORT", 5000))
    print(f"🌍 التشغيل على المنفذ: {port}")
    app.run(host="0.0.0.0", port=port) 
