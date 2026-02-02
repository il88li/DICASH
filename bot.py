import os
from flask import Flask, request
import telebot
import google.generativeai as genai

# --- الإعدادات (تأكد من كتابة التوكن والـ API بشكل صحيح) ---
TOKEN = "8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4"
GEMINI_KEY = "AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE"
CHANNEL_ID = "2904278551"
# الرابط الأساسي بتاعك على ريندر
WEBHOOK_URL = f"https://dicash.onrender.com/webhook"

# تعريف البوت وتطبيق فلاسك
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# إعداد ذكاء Gemini الاصطناعي
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# "البرومبت" اللي بيخلي البوت يلبس الشخصية البائسة الشيك
PROMPT = (
    "تقمص شخصية شاب مصري (16-21 سنة)، شيك جداً وسط ركام حرب. "
    "اكتب عبارة سوداء ساخرة (30 حرف كحد أقصى) بقافية شعبية مصرية دارجة. "
    "ابعد عن الكلمات الرسمية. عبر عن الوسواس ونشافان القلب والأناقة وسط الخراب. "
    "أريد العبارة فقط بدون مقدمات."
)

# --- مسارات الويب هوك (WebHook Routes) ---

@app.route('/webhook', methods=['POST'])
def getMessage():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Forbidden", 403

@app.route('/')
def index():
    # دي عشان لما تفتح الرابط في المتصفح تتأكد إن السيرفر صاحي
    return "<h1>البوت شغال والوجع مستمر..</h1>", 200

# --- معالجة رسائل تلجرام ---

@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.InlineKeyboardMarkup()
    btn = telebot.types.InlineKeyboardButton("نشر نكد شيك في القناة 🖋️", callback_data="publish")
    markup.add(btn)
    bot.reply_to(message, "أهلاً يا برنس.. ده بوت الوجع الشيك. دوس عشان تنشر في القناة.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "publish")
def publish_to_channel(call):
    try:
        # توليد المحتوى بالذكاء الاصطناعي
        response = model.generate_content(PROMPT)
        sad_quote = response.text.strip()
        
        # النشر في القناة
        bot.send_message(CHANNEL_ID, sad_quote)
        
        # الرد على المستخدم في الخاص
        bot.answer_callback_query(call.id, "تم النشر بنجاح.")
        bot.send_message(call.message.chat.id, f"العبارة اللي اتنشرت:\n\n**{sad_quote}**")
    except Exception as e:
        print(f"Error: {e}")
        bot.answer_callback_query(call.id, "حصل مشكلة في التوليد.")

# --- تفعيل الويب هوك وتشغيل التطبيق ---

# ملاحظة: شيلنا الـ set_webhook من جوه الـ main عشان Gunicorn يشغلها فوراً
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

if __name__ == "__main__":
    # تشغيل السيرفر (في حالة التشغيل المحلي أو الاختبار)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
