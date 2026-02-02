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
import requests

# ========== الإعدادات ==========
TOKEN = "8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4"
GEMINI_KEY = "AIzaSyCY5Ltm-Y4ICZYbnNhr7JFK77Ej3-ETSiI"

# استخدام RENDER_EXTERNAL_URL إذا متوفر
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
if RENDER_EXTERNAL_URL:
    WEBHOOK_URL = RENDER_EXTERNAL_URL.rstrip('/')
else:
    WEBHOOK_URL = "https://dicash.onrender.com"

print("=" * 60)
print("🚀 بدء تشغيل برنس النكد مع API الجديد")
print(f"🤖 توكن البوت: {'✅ موجود' if TOKEN else '❌ مفقود'}")
print(f"🧠 مفتاح Gemini: {'✅ موجود' if GEMINI_KEY else '❌ مفقود'}")
print(f"🌐 Webhook URL: {WEBHOOK_URL}")
print("=" * 60)

# ========== تهيئة البوت ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== إدارة الإعدادات ==========
SETTINGS_FILE = 'data/user_settings.json'

def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {
        'channel': "2904278551",
        'time': "غير محدد",
        'is_active': False,
        'created_at': datetime.now().isoformat()
    }

def save_settings(settings):
    try:
        os.makedirs('data', exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الإعدادات: {e}")
        return False

user_settings = load_settings()

# ========== وظيفة توليد العبارات مع API الجديد ==========
def generate_quote():
    """توليد عبارة باستخدام Gemini API مباشرة"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    
    # برومبت عشوائي
    prompts = [
        """أنت شاب مصري (18-21 سنة) برنس في لبسك ستايل بس جواك خربان من 14 سنة حرب.
        اكتب عبارة واحدة مصرية عامية خالص (متعديش 35 حرف)
        بتوصف تناقضك: شيك برا بس دبش جوا، ودنك مع أغاني حب وقلبك ناشف من الحرب.""",
        
        """تقمص شخصية شاب مصري دبش في كلامه بسبب وسواس، برنس في مظهره بس قلبه ناشف من الحرب.
        اكتب جملة واحدة مضحكة-محزنة باللهجة المصرية، متكونش أكتر من 30 حرف.""",
        
        """أنت ولد مصري عايش تناقض: بتسمع أغاني حب وبتفكر في أفكار سوداوية.
        اكتب كلمة وحدة أو جملة صغيرة تعبر عن حالتك النفسية بلغة الشارع المصري."""
    ]
    
    prompt = random.choice(prompts)
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.9,
            "topK": 1,
            "topP": 1,
            "maxOutputTokens": 100
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            if 'candidates' in result and result['candidates']:
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                # تنظيف النص
                text = text.strip()
                text = text.replace('"', '').replace("'", "").replace('`', '')
                
                # إذا كان هناك أسطر متعددة، نأخذ الأول فقط
                if '\n' in text:
                    text = text.split('\n')[0]
                
                # تقصير إذا كان طويلاً
                if len(text) > 50:
                    text = text[:47] + "..."
                
                return text if text else "مفيش كلام النهاردة... 🚬"
            
            else:
                print(f"❌ استجابة API فارغة: {result}")
                return "مش قادر أطلع كلام... جرب تاني"
        
        elif response.status_code == 429:
            print("❌ تجاوز الحد الأقصى للطلبات (Rate Limit)")
            return "كترت الطلبات... استنى شوية ⏳"
        
        else:
            print(f"❌ خطأ API: {response.status_code} - {response.text[:100]}")
            return f"API خطأ {response.status_code}"
            
    except requests.exceptions.Timeout:
        print("❌ انتهت مهلة الطلب")
        return "الطلب أخذ وقت... حاول تاني 🔄"
        
    except Exception as e:
        print(f"❌ خطأ في توليد العبارة: {str(e)}")
        return "الذكاء تعبان النهاردة... 🤒"

# ========== الجدولة ==========
def scheduled_posting():
    if user_settings['is_active'] and user_settings['time'] != "غير محدد":
        try:
            quote = generate_quote()
            channel = user_settings['channel']
            
            if not channel.startswith('@') and not channel.startswith('-100'):
                channel = f"@{channel}" if channel.isdigit() else f"@{channel}"
            
            bot.send_message(channel, quote)
            print(f"✅ [{datetime.now().strftime('%H:%M')}] تم النشر: {quote[:30]}...")
            
        except Exception as e:
            print(f"❌ خطأ في النشر المجدول: {e}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# إعادة جدولة إذا كان نشطاً
if user_settings['is_active'] and user_settings['time'] != "غير محدد":
    try:
        schedule.clear()
        schedule.every().day.at(user_settings['time']).do(scheduled_posting)
    except:
        user_settings['time'] = "غير محدد"
        save_settings(user_settings)

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# ========== واجهة المستخدم ==========
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    status_icon = "✅" if user_settings['is_active'] else "❌"
    
    # عرض مختصر للقناة
    channel_display = user_settings['channel']
    if len(channel_display) > 15:
        channel_display = channel_display[:12] + "..."
    
    markup.add(
        InlineKeyboardButton(f"📢 {channel_display}", callback_data="set_channel"),
        InlineKeyboardButton(f"⏰ {user_settings['time']}", callback_data="set_time"),
        InlineKeyboardButton(f"{status_icon} نشر تلقائي", callback_data="toggle_auto"),
        InlineKeyboardButton("🎭 جيب نكدة", callback_data="gen_private"),
        InlineKeyboardButton("🚀 نزّل في القناة", callback_data="publish_now"),
        InlineKeyboardButton("🔄 جديد", callback_data="different_type")
    )
    return markup

# ========== مسارات Flask ==========
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🎭 برنس النكد</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }
            .bot-link {
                display: inline-block;
                background: #25D366;
                color: white;
                padding: 15px 30px;
                border-radius: 50px;
                text-decoration: none;
                font-size: 1.2em;
                margin: 20px 0;
            }
            .status {
                background: rgba(255, 255, 255, 0.2);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎭 برنس النكد</h1>
            <p>بوت تلجرام للنكد الشيك والتعبير عن التناقض</p>
            
            <div class="status">
                <h3>📊 حالة الخادم</h3>
                <p>✅ الخادم شغال بنجاح</p>
                <p>🤖 Gemini API: ✅ متصل</p>
                <p>📅 الساعة: """ + datetime.now().strftime("%H:%M:%S") + """</p>
            </div>
            
            <a href="https://t.me/""" + bot.get_me().username + """?start=start" class="bot-link" target="_blank">
                🚀 ابدأ مع البوت
            </a>
            
            <div style="margin-top: 30px;">
                <p><a href="/test" style="color: #fff; text-decoration: underline;">🧪 اختبار توليد العبارات</a></p>
                <p><a href="/set_webhook" style="color: #fff; text-decoration: underline;">🔗 تعيين Webhook</a></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return "OK", 200
        except Exception as e:
            print(f"❌ خطأ في معالجة webhook: {e}")
            return "Error", 500
    return "Bad Request", 400

@app.route('/test')
def test():
    """صفحة اختبار توليد العبارات"""
    quote = generate_quote()
    return f"""
    <div style="text-align: center; padding: 50px; font-family: Arial;">
        <h1>🧪 اختبار توليد العبارات</h1>
        <div style="background: #f0f0f0; color: #333; padding: 30px; border-radius: 10px; margin: 20px; font-size: 20px;">
            "{quote}"
        </div>
        <p>طول العبارة: {len(quote)} حرف</p>
        <p><a href="/">🏠 العودة للصفحة الرئيسية</a></p>
    </div>
    """

@app.route('/set_webhook')
def set_webhook():
    """تعيين Webhook يدوياً"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        
        webhook_url = f"{WEBHOOK_URL}/webhook"
        result = bot.set_webhook(url=webhook_url)
        
        # اختبار Webhook
        webhook_info = bot.get_webhook_info()
        
        return f"""
        <h1>✅ تم تعيين Webhook</h1>
        <p>العنوان: {webhook_url}</p>
        <p>النتيجة: {result}</p>
        <p>معلومات Webhook:</p>
        <ul>
            <li>URL: {webhook_info.url}</li>
            <li>عدد الرسائل المنتظرة: {webhook_info.pending_update_count}</li>
            <li>آخر خطأ: {webhook_info.last_error_message or 'لا يوجد'}</li>
        </ul>
        <p><a href="/">🏠 العودة</a></p>
        """
    except Exception as e:
        return f"<h1>❌ خطأ: {e}</h1>"

# ========== معالجة أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    welcome_text = """
🎭 *أهلاً يا برنس!*

*إزاي تستخدم البوت:*

1️⃣ *جيب نكدة* - هتجيلك عبارة تعبر عن تناقضك
2️⃣ *نزّل في القناة* - هينشر العبارة في القناة المحددة
3️⃣ *عدّل الإعدادات* - غير القناة أو الوقت

*أمثلة على العبارات:*
• شيك في البنطال وقلبي رايح هبَال
• ماركات برا وداخلي سجون فاضية
• أهتم بشعري وأخبى من البارود

استخدم الأزرار تحت للتحكم ⬇️
    """
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
🆘 *الأوامر المتاحة:*

/start - بدء البوت وفتح القائمة
/help - عرض هذه الرسالة
/status - حالة البوت والإعدادات
/quote - توليد عبارة عشوائية

*للإعدادات:* استخدم الأزرار في القائمة الرئيسية
    """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_command(message):
    status_text = f"""
📊 *حالة البوت:*

*القناة:* `{user_settings['channel']}`
*الوقت:* `{user_settings['time']}`
*النشر التلقائي:* {'✅ مفعل' if user_settings['is_active'] else '❌ معطل'}
*اسم البوت:* @{bot.get_me().username}

*لتعديل الإعدادات:* استخدم الأزرار
    """
    bot.send_message(message.chat.id, status_text, parse_mode="Markdown")

@bot.message_handler(commands=['quote'])
def quote_command(message):
    """أمر نصي لتوليد عبارة"""
    quote = generate_quote()
    bot.send_message(
        message.chat.id,
        f"🎭 *جبت لك:*\n\n`{quote}`",
        parse_mode="Markdown"
    )

# ========== معالجة الأزرار ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "gen_private":
        quote = generate_quote()
        bot.send_message(
            call.message.chat.id,
            f"🎭 *تفضل يا برنس:*\n\n`{quote}`",
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "✅ جهزت لك")
    
    elif call.data == "publish_now":
        try:
            quote = generate_quote()
            channel = user_settings['channel']
            
            if not channel.startswith('@') and not channel.startswith('-100'):
                channel = f"@{channel}" if channel.isdigit() else f"@{channel}"
            
            bot.send_message(channel, quote)
            bot.send_message(
                call.message.chat.id,
                f"✅ *تم النشر في:* {channel}\n\n`{quote}`",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, "✅ تم النشر")
            
        except Exception as e:
            error_msg = str(e)
            if "chat not found" in error_msg:
                bot.send_message(
                    call.message.chat.id,
                    f"❌ *مش قادر ألاقي القناة:* {user_settings['channel']}\n\n"
                    f"تأكد من:\n"
                    f"1. البوت موجود في القناة\n"
                    f"2. البوت عنده صلاحية النشر\n"
                    f"3. معرف القناة صح"
                )
            else:
                bot.send_message(
                    call.message.chat.id,
                    f"❌ *خطأ في النشر:*\n`{error_msg[:100]}`"
                )
            bot.answer_callback_query(call.id, "❌ فشل النشر")
    
    elif call.data == "different_type":
        quote = generate_quote()
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔄 *جديد من نوع تاني:*\n\n`{quote}`",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id, "🔄 غيرت النمط")
    
    elif call.data == "set_channel":
        msg = bot.send_message(
            call.message.chat.id,
            "📢 *أرسل معرف القناة:*\n\nمثال:\n• @channelname\n• -100xxxxxxx\n• رقم القناة",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, update_channel)
    
    elif call.data == "set_time":
        msg = bot.send_message(
            call.message.chat.id,
            "⏰ *أرسل وقت النشر:*\n\nبصيغة 24 ساعة\nمثال: 14:30 أو 21:00",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, update_time)
    
    elif call.data == "toggle_auto":
        user_settings['is_active'] = not user_settings['is_active']
        save_settings(user_settings)
        
        if user_settings['is_active'] and user_settings['time'] != "غير محدد":
            try:
                schedule.clear()
                schedule.every().day.at(user_settings['time']).do(scheduled_posting)
                status_msg = f"✅ مفعل - ينشر يومياً {user_settings['time']}"
            except:
                status_msg = "❌ وقت غير صحيح"
                user_settings['is_active'] = False
                save_settings(user_settings)
        else:
            schedule.clear()
            status_msg = "❌ معطل"
        
        # تحديث القائمة
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id, status_msg)

def update_channel(message):
    user_settings['channel'] = message.text.strip()
    save_settings(user_settings)
    
    bot.send_message(
        message.chat.id,
        f"✅ *تم تحديث القناة:*\n`{user_settings['channel']}`\n\n"
        f"تأكد البوت موجود في القناة وعنده صلاحية النشر!",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

def update_time(message):
    time_str = message.text.strip()
    
    try:
        if ':' in time_str:
            hours, minutes = map(int, time_str.split(':'))
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                formatted_time = f"{hours:02d}:{minutes:02d}"
                user_settings['time'] = formatted_time
                save_settings(user_settings)
                
                if user_settings['is_active']:
                    schedule.clear()
                    schedule.every().day.at(formatted_time).do(scheduled_posting)
                
                bot.send_message(
                    message.chat.id,
                    f"✅ *تم ضبط الوقت:*\n`{formatted_time}`\n\n"
                    f"سيتم النشر يومياً في هذا الوقت",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
                return
    except:
        pass
    
    bot.send_message(
        message.chat.id,
        "❌ *وقت غير صحيح!*\n\nاستخدم الصيغة: HH:MM\nمثال: 14:30",
        parse_mode="Markdown"
    )

# ========== تشغيل التطبيق ==========
if __name__ == "__main__":
    print("🚀 جاري تشغيل البوت...")
    
    try:
        # معلومات البوت
        bot_info = bot.get_me()
        print(f"🤖 البوت: @{bot_info.username}")
        print(f"👑 الاسم: {bot_info.first_name}")
        print(f"🆔 ID: {bot_info.id}")
        
        # تعيين Webhook
        webhook_url = f"{WEBHOOK_URL}/webhook"
        print(f"🌐 جاري تعيين Webhook على: {webhook_url}")
        
        bot.remove_webhook()
        time.sleep(2)
        
        result = bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook: {result}")
        
        # معلومات Webhook الحالية
        webhook_info = bot.get_webhook_info()
        print(f"📡 معلومات Webhook:")
        print(f"   - URL: {webhook_info.url}")
        print(f"   - Pending updates: {webhook_info.pending_update_count}")
        
        print("=" * 60)
        print("🎉 البوت جاهز للاستخدام!")
        print(f"📱 ابدأ هنا: https://t.me/{bot_info.username}?start=start")
        print("=" * 60)
        
    except Exception as e:
        print(f"⚠️  تحذير في الإعداد: {e}")
    
    # تشغيل Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
