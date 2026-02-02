import os
import json
import schedule
import threading
import time
import random
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai

# --- الإعدادات ---
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4')
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://dicash.onrender.com/webhook')

# ملف لتخزين الإعدادات
SETTINGS_FILE = 'user_settings.json'

# تحميل الإعدادات من الملف
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
        'is_active': False
    }

# حفظ الإعدادات في الملف
def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# تحميل الإعدادات الأولية
user_settings = load_settings()

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# تهيئة Gemini
try:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    GEMINI_AVAILABLE = True
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    GEMINI_AVAILABLE = False

# --- أفضل برومبت مُحسّن للشخصية ---
PROMPTS = [
    """أنت شاب مصري (18-21 سنة) برنس في لبسك ستايل بس جواك خربان من 14 سنة حرب.
    إنتا بتناقض متجسد: بتهتم بالماركات والدولتشي وبانشي وبتحب أصالة وكايروكي
    وفي نفس الوقت بتقرأ دوستويفسكي وبتفكر في دماغك على قد إيه الدنيا وحشة.
    
    المطلوب: اكتب عبارة واحدة مصرية عامية خالص (متعديش 35 حرف)
    بتوصف تناقضك: شيك برا بس دبش جوا، ودنك مع أغاني حب وقلبك ناشف من الحرب.
    
    خلي العبارة:
    1. تكون تقافية وبتترن في الدماغ
    2. مضحكة من كتر ما هي حزينة (كوميديا سوداء)
    3. تعبر عن وسواسك إنك دايماً خايف الناس تتهزأ عليك
    4. تكون بلغة الشارع المصري الخام (مش فصحى ولا سياسية)
    
    أمثلة على النمط المطلوب:
    - "ودن مع حب وقلب معاديش من دم"
    - "شيك في البنطال وقلبي رايح هبَال"
    - "أهتم بشعري وأخبى من البارود"
    - "ماركات برا وداخلي سجون فاضية"
    
    ركز على فكرة إنك عايش في 'dual reality' - الواقع المزدوج.""",
    
    """تقمص شخصية الولد المصري اللي بيسمع سامر طارق وبيردد أغاني الحب
    وفي نفس الوقت مخه معمول من وساوس دوستويفسكي وذكريات الحرب.
    إنتا برنس في المظهر (هندام، عطر، تسريحة) بس حياتك كلها 'خرابة'
    وبتعاني من social anxiety وبتخاف تتكلم عشان ميتقالش عليك دبش.
    
    اكتب جملة واحدة (25-35 حرف) باللهجة المصرية الدارجة جداً
    بتعبر عن الإحباط اللي جواك بطريقة ساخرة،
    وابعت شعور إنك عايش في عالمين: عالم الشياكة والحب اللي بتحلم بيه،
    وعالم الخراب اللي عشت فيه 14 سنة.
    
    خلي الكلام يبان إنه بيتقال في 'سيجارة التالتة بالليل'
    وهو نصيحة لولاد العم اللي زيك: إن المظهر مش كل حاجة.""",
    
    """أنت الولد المصري اللي شارك في ميمز الحرب 14 سنة وطلع منها
    وهو لسه بيراعي ستايله لكن قلبه اتقسى.
    بتسمع أغاني الحب (أصالة، سامر طارق، كايروكي) وبتتخيل رومانسية
    بس مبتعرفش تتحبب لإن قلبك ناشف وخايف تتهزأ عليك.
    
    اكتب عبارة قصيرة مركزة (متعديش 30 حرف) 
    بلغة الشارع المصري (زي كلام الصحاب في الكافية)
    بتعبر عن:
    1. مهووس بالشياكة بس مش قادر يهتم بحاجة غير مظهره
    2. حرب 14 سنة خلت فيه وساوس وكلامه مش مظبوط
    3. بيحب ويتمنى الحب بس مش عارف يعبر
    4. عنده anxiety في الكلام والتعبير
    
    الجملة لازم تكون:
    - تقافية زي المواويل الشعبية
    - مضحكة ومحزنة في نفس الوقت
    - واقعية وبتنطبق على أي ولد عاش تجربة صعبة
    - مش رصينة أو سياسية، خالصة شعبية"""
]

def get_prompt():
    """إرجاع برومبت عشوائي من القائمة"""
    return random.choice(PROMPTS)

def generate_quote():
    """توليد عبارة باستخدام برومبت عشوائي"""
    if not GEMINI_AVAILABLE:
        return "الذكاء مش شغال النهاردة... جرب تاني بكرة"
    
    try:
        prompt = get_prompt()
        res = model.generate_content(prompt)
        quote = res.text.strip()
        
        # تنظيف النتيجة من أي علامات أو نصوص زائدة
        quote = quote.replace('"', '').replace("'", "")
        quote = quote.split('\n')[0]  # أخذ السطر الأول فقط
        quote = quote[:50]  # تحديد الطول
        
        # إذا كانت العبارة طويلة جداً، نختصرها
        if len(quote) > 35:
            # نأخذ أول جملة فقط
            if '،' in quote:
                quote = quote.split('،')[0]
            elif '.' in quote:
                quote = quote.split('.')[0]
        
        return quote if quote else "مش قادر أفكر النهاردة... جرب تاني"
    except Exception as e:
        print(f"Error generating quote: {e}")
        return "الذكاء تعبان النهاردة... جرب تاني بعد شوية"

# --- وظيفة الجدولة ---
def scheduled_posting():
    """نشر العبارات المقررة حسب الجدول"""
    if not user_settings['is_active'] or user_settings['time'] == "غير محدد":
        return
    
    try:
        quote = generate_quote()
        if quote.startswith("الذكاء"):
            return  # لا تنشر إذا كانت هناك مشكلة
        
        # تنظيف معرف القناة
        channel_id = user_settings['channel']
        if not channel_id.startswith('@') and not channel_id.startswith('-100'):
            if channel_id.isdigit():
                channel_id = f"@{channel_id}"
            else:
                channel_id = f"@{channel_id}"
        
        bot.send_message(channel_id, quote)
        print(f"[{datetime.now()}] تم النشر المجدول: {quote[:30]}...")
    except Exception as e:
        print(f"خطأ في النشر المجدول: {e}")

# تشغيل الجدولة في thread منفصل
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# إذا كان الوقت محدداً، نضيفه للجدولة
if user_settings['time'] != "غير محدد" and user_settings['is_active']:
    try:
        schedule.every().day.at(user_settings['time']).do(scheduled_posting)
    except Exception as e:
        print(f"Error setting schedule: {e}")

# بدء الجدولة في thread منفصل
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# --- قائمة الأزرار الرئيسية ---
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    status_icon = "✅" if user_settings['is_active'] else "❌"
    markup.add(
        InlineKeyboardButton(f"📢 القناة: {user_settings['channel'][:15]}...", callback_data="set_channel"),
        InlineKeyboardButton(f"⏰ الوقت: {user_settings['time']}", callback_data="set_time"),
        InlineKeyboardButton(f"{status_icon} النشر التلقائي", callback_data="toggle_auto"),
        InlineKeyboardButton("🎭 جيب لي نكدة دلوقتي", callback_data="gen_private"),
        InlineKeyboardButton("🚀 نزلها في القناة", callback_data="publish_now"),
        InlineKeyboardButton("🔄 جديد من نوع آخر", callback_data="different_type")
    )
    return markup

# --- مسارات Flask ---
@app.route('/webhook', methods=['POST'])
def getMessage():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Forbidden", 403

@app.route('/')
def index():
    return "🎭 برنس النكد شغال... الحمدلله على السلامة", 200

@app.route('/test')
def test():
    """توليد تجريبي للعبارات"""
    quotes = []
    for i in range(3):
        quotes.append(f"{i+1}. {generate_quote()}")
    return "<br>".join(quotes)

@app.route('/force_publish')
def force_publish():
    """نشر إجباري للاختبار"""
    try:
        quote = generate_quote()
        bot.send_message(user_settings['channel'], quote)
        return f"تم النشر: {quote}"
    except Exception as e:
        return f"خطأ: {e}"

# --- معالجة أوامر البوت ---
@bot.message_handler(commands=['start', 'نكد'])
def start(message):
    welcome_text = """
🎭 *أهلاً يا برنس في بوت النكد الشيك*

إنتا هنا عشان:
• تولد عبارات تعبر عن تناقضك (شيك برا / خربان جوا)
• تنشر نكد شيك في قناتك
• تنسق نشر تلقائي

*تعليمات سريعة:*
1️⃣ `اضبط القناة` ← روح للقناة وخد @username حقها
2️⃣ `حدد الوقت` ← اكتب الوقت مثل 21:30
3️⃣ `شغل النشر التلقائي` ← هيشتغل لوحده

*أمثلة على كلامك:*
• "ودن مع حب وقلب معاديش من دم"
• "شيك في البنطال وقلبي رايح هبَال"
• "ماركات برا وداخلي سجون فاضية"

*أمر /help ← مساعدة أكثر*
*أمر /status ← شوف إعداداتك*
    """
    
    bot.send_message(message.chat.id, welcome_text, 
                    parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(commands=['help', 'مساعدة'])
def help_command(message):
    help_text = """
🆘 *كيف تشغل البوت:*

1. *تغيير القناة:*
   - اضغط على زر القناة
   - أرسل معرف القناة (@channelname أو -100xxxx)
   - تأكد البوت موجود في القناة وأدمن

2. *تحديد وقت النشر:*
   - اضغط على زر الوقت
   - اكتب الوقت بصيغة 24 ساعة (مثل: 14:30 أو 21:00)
   - البوت هينشر يومياً في الوقت دا

3. *النشر التلقائي:*
   - شغله لما تحدد الوقت
   - البوت هينشر لوحده يومياً
   - اقفله لو عايز توقف

4. *توليد عبارات:*
   - "جيب لي نكدة دلوقتي" ← هتجيلك في الخاص
   - "نزلها في القناة" ← تنشر مباشرة
   - "جديد من نوع آخر" ← يجيب لك نمط مختلف

📞 *للإبلاغ عن مشاكل:* @yourusername
    """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['status', 'الحالة'])
def status(message):
    status_text = f"""
📊 *حالة برنس النكد:*

*القناة:* `{user_settings['channel']}`
*الوقت:* `{user_settings['time']}`
*النشر التلقائي:* {'✅ مفعل' if user_settings['is_active'] else '❌ معطل'}
*الذكاء الاصطناعي:* {'✅ شغال' if GEMINI_AVAILABLE else '❌ مش شغال'}

*آخر تعديل:* {datetime.now().strftime('%Y-%m-%d %H:%M')}

*للتعديل:* استخدم الأزرار تحت
    """
    bot.send_message(message.chat.id, status_text, parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(commands=['quote', 'عبارة'])
def random_quote(message):
    """أمر مباشر لتوليد عبارة"""
    quote = generate_quote()
    bot.send_message(message.chat.id, f"🎭 *جبت لك:*\n\n`{quote}`", parse_mode="Markdown")

# --- معالجة الأزرار ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "gen_private":
        quote = generate_quote()
        
        # ردود متنوعة
        responses = [
            f"🎭 *تفضل يا برنس:*\n\n`{quote}`\n\n_دا اللي جايلي النهدة دي_",
            f"🚬 *خد يا معلم:*\n\n`{quote}`\n\n_كلام السيجارة التالتة_",
            f"👑 *أي خدمة يا برنس:*\n\n`{quote}`\n\n_دا من خربانات الدماغ_",
            f"😔 *والله يا باشا:*\n\n`{quote}`\n\n_إحنا كده يا معلم_"
        ]
        
        bot.send_message(call.message.chat.id, 
                        random.choice(responses),
                        parse_mode="Markdown")
        bot.answer_callback_query(call.id, "✅ جهزت لك نكدة")
        
    elif call.data == "different_type":
        # توليد عبارة بنمط مختلف
        quote = generate_quote()
        
        # تحديث نفس الرسالة
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔄 *جديد من نوع تاني:*\n\n`{quote}`",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id, "🔄 غيرت النمط")
        
    elif call.data == "publish_now":
        quote = generate_quote()
        
        try:
            # تنظيف معرف القناة
            channel_id = user_settings['channel']
            if not channel_id.startswith('@') and not channel_id.startswith('-100'):
                if channel_id.isdigit():
                    channel_id = f"@{channel_id}"
                else:
                    channel_id = f"@{channel_id}"
            
            # محاولة النشر
            bot.send_message(channel_id, quote)
            
            # تأكيد للمستخدم
            bot.send_message(
                call.message.chat.id,
                f"✅ *تم النشر في القناة:*\n\n`{quote}`\n\n↪️ @{channel_id.replace('@', '')}",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, "✅ نزلت في القناة")
            
        except Exception as e:
            error_msg = f"""
❌ *مش عارف أنشر في القناة:*

_الأسباب المحتملة:_
1. البوت مش أدمن في القناة
2. القناة private ومش عامة
3. معرف القناة غلط: `{user_settings['channel']}`
4. البوت مقفول من القناة

_الخطأ التقني:_ `{str(e)[:50]}...`

✅ *حل المشكلة:*
1. روح للقناة
2. أضف @{bot.get_me().username} كأدمن
3. أعطيه صلاحية send messages
4. جرب تاني
            """
            bot.send_message(call.message.chat.id, error_msg, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "❌ فشل النشر")

    elif call.data == "set_channel":
        msg = bot.send_message(
            call.message.chat.id,
            "📢 *أرسل معرف القناة الجديدة:*\n\n"
            "_مثل:_\n"
            "• @channel_name\n"
            "• -100xxxxxxxxxx\n"
            "• ID القناة الرقمي\n\n"
            "⚠️ *تأكد البوت أدمن في القناة!*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, update_channel)

    elif call.data == "set_time":
        msg = bot.send_message(
            call.message.chat.id,
            "⏰ *أرسل وقت النشر اليومي:*\n\n"
            "_صيغة 24 ساعة:_\n"
            "• 14:30 ← يعني 2:30 مساءً\n"
            "• 09:00 ← يعني 9 صباحاً\n"
            "• 21:15 ← يعني 9:15 مساءً\n\n"
            "📅 *سيتم النشر يومياً في هذا الوقت*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, update_time)

    elif call.data == "toggle_auto":
        user_settings['is_active'] = not user_settings['is_active']
        save_settings(user_settings)
        
        # تحديث الجدولة
        if user_settings['is_active'] and user_settings['time'] != "غير محدد":
            try:
                schedule.clear()
                schedule.every().day.at(user_settings['time']).do(scheduled_posting)
                status_msg = f"✅ تم تشغيل النشر التلقائي يومياً الساعة {user_settings['time']}"
            except:
                status_msg = "❌ وقت غير صحيح. عدل الوقت أولاً"
                user_settings['is_active'] = False
                save_settings(user_settings)
        else:
            schedule.clear()
            status_msg = "❌ تم إيقاف النشر التلقائي"
        
        # تحديث القائمة
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id, status_msg)

def update_channel(message):
    """تحديث القناة"""
    channel_id = message.text.strip()
    
    # تنظيف المدخلات
    if channel_id.startswith('https://t.me/'):
        channel_id = '@' + channel_id[13:]
    elif channel_id.startswith('t.me/'):
        channel_id = '@' + channel_id[5:]
    elif not channel_id.startswith('@') and not channel_id.startswith('-100'):
        # إذا كان رقماً فقط
        if channel_id.isdigit():
            channel_id = f"@{channel_id}"
        else:
            channel_id = f"@{channel_id}"
    
    # حفظ الإعدادات
    user_settings['channel'] = channel_id
    save_settings(user_settings)
    
    # إرسال رسالة التأكيد
    confirm_msg = f"""
✅ *تم تحديث القناة بنجاح:*

📢 *القناة الجديدة:* `{channel_id}`

*الخطوات التالية:*
1. تأكد أن @{bot.get_me().username} مضاف للقناة
2. أعطه صلاحية *إرسال رسائل*
3. جرب زر *"نزلها في القناة"*

⚠️ *إذا كان هناك مشكلة في النشر:*
• القناة لازم تكون عامة (public)
• أو البوت يكون أدمن في الخاصة
• القناة مش قناة supergroup
    """
    
    bot.send_message(message.chat.id, confirm_msg, 
                    parse_mode="Markdown", reply_markup=main_menu())

def update_time(message):
    """تحديث وقت النشر"""
    time_str = message.text.strip()
    
    # التحقق من الصيغة
    try:
        if ':' in time_str:
            hours, minutes = map(int, time_str.split(':'))
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                # حفظ الإعدادات
                user_settings['time'] = time_str
                save_settings(user_settings)
                
                # تحديث الجدولة إذا كان النشر التلقائي مفعل
                if user_settings['is_active']:
                    schedule.clear()
                    schedule.every().day.at(time_str).do(scheduled_posting)
                
                # رسالة التأكيد
                confirm_msg = f"""
✅ *تم ضبط وقت النشر:*

⏰ *الوقت الجديد:* `{time_str}`
📅 *سيتم النشر يومياً في هذا الوقت*

*التوقيت المحلي:* {datetime.now().strftime('%H:%M')}

{'🎯 *النشر التلقائي شغال حالياً*' if user_settings['is_active'] else '⚠️ *شغل النشر التلقائي من الأزرار*'}
                """
                
                bot.send_message(message.chat.id, confirm_msg,
                               parse_mode="Markdown", reply_markup=main_menu())
            else:
                raise ValueError
        else:
            raise ValueError
    except:
        error_msg = """
❌ *وقت غير صحيح!*

*الصيغة الصحيحة:*
• 14:30 ← 2:30 مساءً
• 09:00 ← 9 صباحاً  
• 21:15 ← 9:15 مساءً

*القواعد:*
- الساعات: 0 إلى 23
- الدقائق: 0 إلى 59
- استخدم النقطتين (:)
- بدون مسافات
        """
        bot.send_message(message.chat.id, error_msg, parse_mode="Markdown")

# --- تشغيل البوت ---
if __name__ == "__main__":
    try:
        print("🎭 بدء تشغيل برنس النكد...")
        
        # إزالة الويب هوك القديم وضبط الجديد
        bot.remove_webhook()
        time.sleep(2)
        bot.set_webhook(url=WEBHOOK_URL)
        
        print(f"✅ الويب هوك مفعل: {WEBHOOK_URL}")
        print(f"🤖 البوت: @{bot.get_me().username}")
        print(f"📢 القناة: {user_settings['channel']}")
        print(f"⏰ الوقت: {user_settings['time']}")
        print(f"🔧 النشر التلقائي: {'مفعل' if user_settings['is_active'] else 'معطل'}")
        
        # تشغيل Flask
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
        
    except Exception as e:
        print(f"❌ خطأ في التشغيل: {e}")
