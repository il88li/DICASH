import os
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai

# --- الإعدادات ---
TOKEN = "8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4"
GEMINI_KEY = "AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE"
CHANNEL_ID = "2904278551"
URL = "https://dicash.onrender.com" # الرابط الخاص بك على Render

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# إعداد Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

PROMPT = """
تقمص شخصية شاب مصري (16-21 سنة)، شيك جداً وسط ركام حرب. 
اكتب عبارة سوداء ساخرة (25-30 حرف) بقافية شعبية مصرية دارجة. 
ابعد عن الكلمات الرسمية. عبر عن الوسواس ونشافان القلب والأناقة وسط الخراب. 
أريد العبارة فقط.
"""

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=URL + '/' + TOKEN)
    return "البوت شغال والويب هوك متفعل يا برنس!", 200

@bot.message_handler(commands=['start'])
def start(message):
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("توليد ونشر نكد مقفي 🖋️", callback_data="publish")
    markup.add(btn)
    bot.reply_to(message, "أهلاً يا برنس.. جاهز تنشر نكد شيك؟", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "publish")
def publish(call):
    try:
        response = model.generate_content(PROMPT)
        quote = response.text.strip()
        bot.send_message(CHANNEL_ID, quote)
        bot.answer_callback_query(call.id, "تم النشر بنجاح.")
        bot.send_message(call.message.chat.id, f"المنشور:\n{quote}")
    except:
        bot.send_message(call.message.chat.id, "حصل مشكلة في التوليد.")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
