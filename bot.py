import os
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai

# --- الإعدادات ---
TOKEN = "8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4"
GEMINI_KEY = "AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE"
WEBHOOK_URL = "https://dicash.onrender.com/webhook"

# متغيرات لحفظ الإعدادات مؤقتاً (يفضل لاحقاً استخدام قاعدة بيانات)
user_settings = {
    'channel': "2904278551",
    'time': "غير محدد"
}

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

PROMPT = "تقمص شخصية شاب مصري (16-21 سنة)، 'برنس' في لبسه وذوقه عالي جداً، بس حياته عبارة عن 'خرابة' بسبب 14 سنة حرب في وطنه. أنت شخصية متناقضة: مهووس بهيبة الدكتاتور وكآبة دوستويفسكي، وودنك مع أصالة وسامر طارق وكايروكي.
​قواعد الكلام والتعامل:
​اللغة: مصرية عامية دارجة جداً (لغة شارع)، وابعد تماماً عن الكلمات العربية الرسمية أو السياسية (زي استبد، ساد، هدد).
​الأسلوب: عبارات مقتضبة (25-30 حرف) ليها قافية شعبية صايعة، مضحكة من كتر ما هي محزنة.
​العقد النفسية: وضح إنك 'دبش' في الكلام بسبب الوسواس، ومبتعرفش تحب بسبب نشافان القلب من الحرب، وبتخاف تنطق نكتة أو تتكلم قدام ناس عشان ميتريقوش عليك.
​المطلوب: فضفض عن بؤسك وتناقضك بكلمات 'ترن' في الدماغ وتوصف حالك كواحد شيك وسط الردم"

# --- قائمة الأزرار الرئيسية ---
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"📢 القناة الحالية: {user_settings['channel']}", callback_data="set_channel"),
        InlineKeyboardButton(f"⏰ وقت النشر: {user_settings['time']}", callback_data="set_time"),
        InlineKeyboardButton("🖋️ توليد عبارة في الشات هنا", callback_data="gen_private"),
        InlineKeyboardButton("🚀 أنشر نكد في القناة فوراً", callback_data="publish_now")
    )
    return markup

# --- مسار استقبال الويب هوك ---
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
    return "Bot is Alive!", 200

# --- معالجة الأوامر ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "لوحة تحكم البرنس لبث النكد الشيك:", reply_markup=main_menu())

# --- معالجة الأزرار ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "gen_private":
        try:
            res = model.generate_content(PROMPT)
            bot.send_message(call.message.chat.id, f"تفضل يا برنس:\n\n`{res.text.strip()}`", parse_mode="Markdown")
        except:
            bot.answer_callback_query(call.id, "الذكاء الاصطناعي معلق..")
            
    elif call.data == "publish_now":
        try:
            res = model.generate_content(PROMPT)
            quote = res.text.strip()
            bot.send_message(user_settings['channel'], quote)
            bot.answer_callback_query(call.id, "تم النشر في القناة!")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"فشل النشر. تأكد من وجود البوت كأدمن في القناة {user_settings['channel']}")

    elif call.data == "set_channel":
        msg = bot.send_message(call.message.chat.id, "أرسل المعرف الجديد للقناة (مثلاً @username):")
        bot.register_next_step_handler(msg, update_channel)

    elif call.data == "set_time":
        msg = bot.send_message(call.message.chat.id, "أرسل الوقت الجديد للنشر (مثلاً 10:00 PM):")
        bot.register_next_step_handler(msg, update_time)

def update_channel(message):
    user_settings['channel'] = message.text
    bot.send_message(message.chat.id, f"تم تغيير القناة لـ: {message.text}", reply_markup=main_menu())

def update_time(message):
    user_settings['time'] = message.text
    bot.send_message(message.chat.id, f"تم ضبط الوقت لـ: {message.text}", reply_markup=main_menu())

# --- تفعيل الويب هوك عند التشغيل ---
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
